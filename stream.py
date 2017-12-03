#!/usr/bin/env python

import re
import json
import threading
import RPi.GPIO as GPIO
import random

from tweepy.streaming import StreamListener
from tweepy import OAuthHandler
from tweepy import Stream

from config import OAUTH_KEYS
from config import MOOD_LIMIT
from config import MOOD_COLORS
from config import MOOD_FOLDER
from config import LED_PINS
from config import LED_COLORS

from datetime import datetime, time

def setInterval(interval):
    def decorator(function):
        def wrapper(*args, **kwargs):
            stopped = threading.Event()

            def loop(): # executed in another thread
                while not stopped.wait(interval): # until stopped
                    function(*args, **kwargs)

            t = threading.Thread(target=loop)
            t.daemon = True # stop if the program exits
            t.start()
            return stopped
        return wrapper
    return decorator

class MoodChecker(object):
    def __init__(self, ledcontroller):
        super(MoodChecker, self).__init__()
        self.ledcontroller = ledcontroller
        self.emotion_stack = list()
        self.match_phrases = list()
        self.emotion_index = dict()
        for mood_name in MOOD_COLORS:
            # start each emotion name at 0
            self.emotion_index[mood_name] = 0
            # read the word lists in and index them by emotion
            mood_file = MOOD_FOLDER + "/" + mood_name + ".txt"
            with open(mood_file) as f:
                mood_matches = f.readlines()
                for mood_match in mood_matches:
                    print mood_name + " => " + mood_match.strip()
                    pattern = re.compile(mood_match.strip(), re.I)
                    self.match_phrases.append((mood_name, pattern))


    def match_phrase(self, tweet_text):
        for emotion, pattern in self.match_phrases:
            if pattern.match(tweet_text):
                print "Emotion: " + emotion
		#print "Pattern: "
                #print pattern
                #print "Text: " + tweet_text
                self.stack_emotion(emotion)


    def stack_emotion(self, emotion):
        self.emotion_stack.append(emotion)
        #print self.emotion_stack
        self.emotion_index[emotion] = self.emotion_index[emotion] + 1

        if MOOD_LIMIT < len(self.emotion_stack):
            oldest_emotion = self.emotion_stack.pop(0)
            self.emotion_index[oldest_emotion] = self.emotion_index[oldest_emotion] - 1

    def show_current_emotion(self):
        print self.emotion_index
	current_max_val = max(self.emotion_index.values())
	#print current_max_val
	winning_key = random.choice([k for (k, v) in self.emotion_index.items() if v == current_max_val])
        color = MOOD_COLORS[winning_key]
        print winning_key + " => " + color
        self.ledcontroller.led_show_rgb(LED_COLORS[color])

    def reset_emotion_index(self):
	print "Resetting emotion index..."
	for mood_name in MOOD_COLORS:
            self.emotion_index[mood_name] = 0
            

class MoodListener(StreamListener):
    def load_word_list(self, ledcontroller):
        self.checker = MoodChecker(ledcontroller)
	self.interval_time = datetime.now()

    def sample(self):
        self.checker.show_current_emotion()
	now_time = datetime.now()
	print now_time 
	tdelta = now_time - self.interval_time
	print tdelta.seconds
	if tdelta.seconds >= 600:
		self.checker.reset_emotion_index()
		self.interval_time = now_time

    def stop_sampling(self):
        self.sample_timer.cancel()

    def on_data(self, data):
        tweet = json.loads(data)
        tweet_text = tweet.get('text')
        # print tweet_text
        if None != tweet_text and '' != tweet_text:
            self.checker.match_phrase(tweet_text)
        return True

    def on_error(self, status):
        print status


class LightController(object):
    def bind_to_gpio(self, led_pins):
        GPIO.setmode(GPIO.BOARD)

        self.red_pwm = self.start_pwm(led_pins['red'])
        self.green_pwm = self.start_pwm(led_pins['green'])
        self.blue_pwm = self.start_pwm(led_pins['blue'])

        self.current_color = 0

    def start_pwm(self, pin_id):
        pwm_frequency = 60 # Hz
        GPIO.setup(pin_id, GPIO.OUT)
        pwm = GPIO.PWM(pin_id, pwm_frequency)
        pwm.start(0)
        return pwm

    def led_show_rgb(self, rgb_color):
        if self.current_color == rgb_color:
            return

        r = (rgb_color >> 16) & 0xFF
        g = (rgb_color >> 8) & 0xFF
        b = rgb_color & 0xFF

        self.red_pwm.ChangeDutyCycle(100 * r / 255)
        self.green_pwm.ChangeDutyCycle(100 * g / 255)
        self.blue_pwm.ChangeDutyCycle(100 * b / 255)

        self.curent_color = rgb_color

    def cleanup(self):
        self.red_pwm.stop()
        self.green_pwm.stop()
        self.blue_pwm.stop()
        GPIO.cleanup()


@setInterval(5)
def update_output():
    listener.sample()


if __name__ == '__main__':
    try:
        ledcontroller = LightController()
        ledcontroller.bind_to_gpio(LED_PINS)

        listener = MoodListener()
        listener.load_word_list(ledcontroller)

        output_interval = update_output()

        auth = OAuthHandler(OAUTH_KEYS['consumer_key'], OAUTH_KEYS['consumer_secret'])
        auth.set_access_token(OAUTH_KEYS['access_token_key'], OAUTH_KEYS['access_token_secret'])

        stream = Stream(auth, listener)
        # stream.filter(track=['basketball'])
        # stream.sample(async=True)
        stream.sample()

    except (KeyboardInterrupt, SystemExit):
        print '\n! Received keyboard interrupt, quitting threads.\n'
        output_interval.set()
        GPIO.cleanup()

    except Exception, e:
	print("Unexpected error!!!",e)
	output_interval.set()
	GPIO.cleanup()
