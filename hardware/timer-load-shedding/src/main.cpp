#include <Arduino.h>
const int SHED1_PIN = 26; // red led
const int SHED2_PIN = 32; // yellow led
const int PROTECTED_PIN = 27; // green led


int shedStage = 0;

// basically at least per the github red and yellow are low priority so we shed those only and keep the main one running (the main rail)

void setup() {
    pinMode(SHED1_PIN, OUTPUT); // sets pin 26 to send voltage
    pinMode(SHED2_PIN, OUTPUT); // sets pin 32 to send voltage
    pinMode(PROTECTED_PIN, OUTPUT); // sets pin 27 to send voltage

    // Startup: all three loads begin ON (powered).
    // LED on = load running. Green is protected and never shed.
    digitalWrite(SHED1_PIN, HIGH);
    digitalWrite(SHED2_PIN, HIGH);
    digitalWrite(PROTECTED_PIN, HIGH);
}

void shed_step() {
    if(shedStage == 0) {
        digitalWrite(SHED1_PIN, LOW);
    }

    if(shedStage == 1) {
        digitalWrite(SHED2_PIN, LOW);
    }
    
    // keeps shedStage to only go from 0 to 1
    if (shedStage < 2) { 
        shedStage = shedStage + 1; // moves the counter forward by one 
    }
}

void loop() {
    // // testing if all 3 leds blink
    // digitalWrite(SHED1_PIN, HIGH); // led on
    // delay(500); // wait 500 ms
    // digitalWrite(SHED1_PIN, LOW); // LED off
    // delay(500); // wait 500 ms again

    // digitalWrite(SHED2_PIN, HIGH); // led on
    // delay(500); // wait 500 ms
    // digitalWrite(SHED2_PIN, LOW); // LED off
    // delay(500); // wait 500 ms again

    // digitalWrite(PROTECTED_PIN, HIGH); // led on
    // delay(500); // wait 500 ms
    // digitalWrite(PROTECTED_PIN, LOW); // LED off
    // delay(500); // wait 500 ms again

    delay(8000);
    shed_step();

}

