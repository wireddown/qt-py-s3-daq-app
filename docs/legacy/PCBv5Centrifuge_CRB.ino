/* Ports and Pins

 Direct port access is much faster than digitalWrite.
 You must match the correct port and pin as shown in the table below.

 Arduino Pin        Port        Pin
 13 (SCK)           PORTB       5
 12 (MISO)          PORTB       4
 11 (MOSI)          PORTB       3
 10 (SS)            PORTB       2
 9                  PORTB       1
 8                  PORTB       0
 7                  PORTD       7
 6                  PORTD       6
 5                  PORTD       5
 4                  PORTD       4
 3                  PORTD       3
 2                  PORTD       2
 1 (TX)             PORTD       1
 0 (RX)             PORTD       0
 A5 (Analog)        PORTC       5
 A4 (Analog)        PORTC       4
 A3 (Analog)        PORTC       3
 A2 (Analog)        PORTC       2
 A1 (Analog)        PORTC       1
 A0 (Analog)        PORTC       0

 */

/*
Chip Select Line:
ADC	Jeenode Port	Jeenode Connection	Corresponding Arduino Port
#1	    p1	              digital              	PD4
#2	    p4	              digital            	PD7
#3	    p2                analog            	PC1
#4	    p3	              analog	                PC2
SPI Comm (common):
Data in  	p2	      digital            	PD5
SPI clock	p3            digital            	PD6
*/

/*

PORT    Jee     Arduino     Jee         Arduino
1      DIO1       4        AIO1          A0
2      DIO2       5        AIO2          A1
3      DIO3       6        AIO3          A2
4      DIO4       7        AIO4          A3


*/


//#define RFM69_COMPAT 1  //This is for backward compatibility with the RF12 drivers. New Boards as of at least 2018 use the RFM69, rather than the RF12. for old boards, omit this line of code
#include <JeeLib.h>
#include <avr/sleep.h>
#include <stdarg.h>

// boilerplate for low-power waiting
ISR(WDT_vect) {
  Sleepy::watchdogEvent();
}


#define MPCS 7
#define MPDAT1 A2
#define MPCLK A3

#define RF12_SLEEP 0
#define RF12_WAKEUP -1
#define POWEROUT 4

#define ADCCS A0 //old
#define ADCCS 6
#define ADCDAT 5
#define ADCCLK A1

struct {
  long int start;   // time byte sent
  long int later;   // how long we had to wait for packet to come in
} payload;

static long int data[9];

typedef struct {
  long int r0;
  long int r1;
  long int r2;
  long int r3;
  long int r4;
  long int r5;
  long int r6;
  long int r7;
  long int r8;
} Payload;

static Payload sendpackage;

int tester;
int hasData;
static int confirmed;
long int tempValue;
long int tempValue2;

typedef struct {
  char r1;
  char r2;
  char r3;
  char r4;
} cflags;

static cflags FLAGS;
int counter;
static bool ackconf;
static long int ReadingSchedule;



void setup() {
  Serial.begin(9600); //57600 //9600
  //rf12_initialize(ID,FREQUENCY,GROUP)
  //ID = Unique #
  //FREQUENCY can be : RF12_433MHZ or RF12_915MHZ
  //GROUP Should Correspond to which centrifuge the program is loaded on (e.g. 1,2, or 3)

  //for (int i=3; i>=0; i--){
  //Serial.println("asdf");
  //}
  pinMode(POWEROUT, OUTPUT);
  digitalWrite(POWEROUT, HIGH);
  pinMode(ADCCS, OUTPUT); // chip select ADC
  pinMode(ADCDAT, INPUT); // input
  pinMode(ADCCLK, OUTPUT); // clock
  digitalWrite(ADCCS, HIGH);
  pinMode(MPCS, OUTPUT); // chip select multiplexer
  pinMode(MPDAT1, OUTPUT); // data 1
  digitalWrite(MPCS, LOW);
  pinMode(MPCLK, OUTPUT); // clock for multiplexer
  rf12_initialize(21, RF12_433MHZ, 10);  //or 915MHZ or 433
  Serial.println("LTC2400 ADC Test");

  FLAGS.r1 = '0';
  FLAGS.r2 = '0';
  FLAGS.r3 = '0';
  FLAGS.r4 = '2';


  //Serial.println("Setup Done");
  //digitalWrite(POWEROUT, LOW);
  // test channel select - This is where you change the frequency which is used


}


void loop() {
// INTERACTIVE OPERATION: WAIT FOR COMMAND, & READ
  while (FLAGS.r1 == '1') {

    if (rf12_recvDone() && rf12_crc == 0) {
      ackconf = false;
      
      FLAGS.r4 = (char) (rf12_data[3]);
      FLAGS.r3 = (char) (rf12_data[2]);
      FLAGS.r2 = (char) (rf12_data[1]);
      FLAGS.r1 = (char) (rf12_data[0]);


      if (RF12_WANTS_ACK) {
        Serial.println("Wants Ack");
        while (!ackconf) {
          if (rf12_canSend()) {
            rf12_sendStart(RF12_ACK_REPLY,0,0);
            rf12_sendWait(1);
            ackconf = true;
          } else {
            delay(20);
            rf12_recvDone();
            Serial.println("Waiting to Acknowledge");
          }
        }


      }

      Serial.println("FLAGS =");
      Serial.println(FLAGS.r1);
      Serial.println(FLAGS.r2);
      Serial.println(FLAGS.r3);
      Serial.println(FLAGS.r4);
      delay(50);
      
      if (FLAGS.r2 == '1') {
        Serial.println("Reading Sensors per Request");
        read_sensors();
        transmit_data();
        FLAGS.r2 = '0';    //reset 'read' flag
        Serial.println("Resetting Read Flag:");
        Serial.println(FLAGS.r2);
        delay(20);
      }

    }
  }

  // RESUME NORMAL OPERATION: READ & SLEEP
  //Sleepy::loseSomeTime(450);
  delay(50);
  read_sensors();
  transmit_data();
  if (FLAGS.r4 == '1'){
    ReadingSchedule = 60000;
  }else if (FLAGS.r4 == '2'){
    ReadingSchedule = 20000;
  }else if (FLAGS.r4 == '3'){
    ReadingSchedule = 3300;
  }else {
    ReadingSchedule = 60000;
  }
 
  
  if (FLAGS.r1 == '0'){

  Serial.println("Sleep Now");
  delay(50);
  rf12_sleep(RF12_SLEEP);
  digitalWrite(POWEROUT, LOW);
  //delay(22200);
  for(byte i=0; i<3; i++){
  Sleepy::loseSomeTime(ReadingSchedule);
  }
  delay(50);
  digitalWrite(POWEROUT, HIGH);
  delay(300);
  rf12_sleep(RF12_WAKEUP);
  rf12_recvDone();
  }


}



void read_sensors() {
  for (int i = 0; i < 8; i++) {
    channel_select(i);
    delay(10);
    //Serial.print(i);
    tempValue = read_adc(ADCCS);
    delay(165);
    tempValue = read_adc(ADCCS);
    delay(165);
    tempValue2 = read_adc(ADCCS);
    data[i] = (tempValue2 + tempValue) / 2;
    data[i] >>= 8;

    //Serial.print(" ");
    //Serial.print(data[i]);
    //Serial.print(" ");
    //Serial.println(data[i]/65536.0);
    //Serial.println("Reading Data");
    delay(155);
  }
  data[8] = analogRead(A0);
  data[8] = analogRead(A0);

  hasData = 1;
  confirmed = 0;

}


void transmit_data() {
  sendpackage.r0 = data[0];
  sendpackage.r1 = data[1];
  sendpackage.r2 = data[2];
  sendpackage.r3 = data[3];
  sendpackage.r4 = data[4];
  sendpackage.r5 = data[5];
  sendpackage.r6 = data[6];
  sendpackage.r7 = data[7];
  sendpackage.r8 = data[8];
  delay(20);
  tester = 0;
  if (tester == 0) {
    delay(20);
    while (hasData == 1 || confirmed == 0) {
      if (hasData == 0) {
        payload.later = (long int) millis() - payload.start;
        if (rf12_recvDone() && rf12_crc == 0) {
          confirmed = 1;

          Serial.println("Ack. recvd.");
          FLAGS.r4 = (char) (rf12_data[3]);
          FLAGS.r3 = (char) (rf12_data[2]);
          FLAGS.r2 = (char) (rf12_data[1]);
          FLAGS.r1 = (char) (rf12_data[0]);
          Serial.println("FLAGS =");
          Serial.println(FLAGS.r1);
          Serial.println(FLAGS.r2);
          Serial.println(FLAGS.r3);
          Serial.println(FLAGS.r4);
        }
        else if (payload.later > 1500) {
          Serial.println("No Ack., resending.");
          hasData = 1;
          delay(20);
        }
      }
      else if (hasData == 1) {
        if (rf12_canSend()) {
          hasData = 0;
          //Serial.println(sizeof sendpackage);
          rf12_sendStart(RF12_HDR_ACK, &sendpackage, sizeof sendpackage);
          rf12_sendWait(1);
          payload.start = millis();
          Serial.println("Sending Data");
          delay(20);

        }
        else {
          delay(500);
          rf12_recvDone();
          Serial.println("rf12 can't send, waiting.");
        }
      }
    }
  }
}




void channel_select(int chan) {


  digitalWrite(MPCLK, LOW);
  digitalWrite(MPCS, HIGH);

  digitalWrite(MPDAT1, HIGH); // EN bit
  digitalWrite(MPCLK, LOW);
  digitalWrite(MPCLK, HIGH);

  for (int i = 2; i > -1; i--) {
    int temp = chan;
    temp >>= i;

    if (temp & 1) {
      digitalWrite(MPDAT1, HIGH);
      digitalWrite(MPCLK, LOW);
      digitalWrite(MPCLK, HIGH);
    } else {
      digitalWrite(MPDAT1, LOW);
      digitalWrite(MPCLK, LOW);
      digitalWrite(MPCLK, HIGH);
    }
  }

  digitalWrite(MPCS, LOW);
  digitalWrite(MPDAT1, LOW);
  digitalWrite(MPCLK, LOW);
}


// //this is the function to read a value from the ADC using SPI serial interface
////the input is the chip select pin for the ADC we want to read, the returned value is the read ADC value
long int read_adc(char csPIN)
{
  long int adcvalue = 0;
  int resultSign = 1;
  int resultExt = 0;
  int numberOfDataBits = 23;
  //Serial.println("TEST1");

  //set the chip select pin to LOW for the specific ADC, this tells the ADC we want a reading from it
  digitalWrite(csPIN, LOW);

  //Serial.println("Setting csPIN to Low");
  //the ADC keeps the DATAIN (output from ADC, input to arduino) at HIGH after the chip select for the ADC
  //has been set to low until it is ready to send us data.  It takes a few ms for the ADC to read a value
  while (digitalRead(ADCDAT) == HIGH) {
    //wait for ready
    //Serial.println("stuck");
    delay(150);

  }

  //double checking that DATAIN is low and ADC is ready to send data
  //see SPI serial communication documents (ADC manual has this included I think) for more details on SPI stuff
  if (digitalRead(ADCDAT) == LOW) {
    //read bits from adc
    //ignore first 4 bits of data, junk data
    //      for (int i=3; i>=0; i--){
    //          //Serial.print(digitalRead(DATAIN));
    //          //cycle clock
    //          digitalWrite(ADCCLK,HIGH);
    //          digitalWrite(ADCCLK,LOW);
    //      }
    //bit 31 EOC
    //bit 30 DMY
    digitalWrite(ADCCLK, HIGH);
    digitalWrite(ADCCLK, LOW);
    //bit 29 SIGN
    digitalWrite(ADCCLK, HIGH);
    digitalWrite(ADCCLK, LOW);
    if (digitalRead(ADCDAT) == LOW) {
      resultSign = -1;
    }
    //bit 28 EXT
    digitalWrite(ADCCLK, HIGH);
    digitalWrite(ADCCLK, LOW);
    if (digitalRead(ADCDAT) == HIGH) {
      resultExt = 1;
    }
    //bit 27 MSB
    digitalWrite(ADCCLK, HIGH);
    digitalWrite(ADCCLK, LOW);
    //Serial.print(" ");
    //read remaining 24 bits of "useful" data even though we remove the last 8 bits later on
    for (int i = numberOfDataBits; i >= 0; i--) {
      //read the bit, 0 or 1, eg. 1 and bit add to ADCvalue
      adcvalue |= digitalRead(ADCDAT);
      //Serial.print(digitalRead(ADCDAT));
      //shift the bit left once, resulting in eg. 10
      adcvalue <<= 1;
      //<<i;
      //Serial.print(digitalRead(DATAIN));
      //cycle clock to signify we want next bit
      digitalWrite(ADCCLK, HIGH);
      digitalWrite(ADCCLK, LOW);
    }
    //Serial.print(" ");
    //not sure why I'm shifting the bits right once here, I guess I didn't want the last bit I read? check ADC manual
    adcvalue >>= 1;
    //Serial.println(adcvalue);
  }
  if (resultExt == 1) {
    if (resultSign == 1) {
      adcvalue = adcvalue + 16777216;
    }
    if (resultSign == -1) {
      adcvalue = adcvalue - 16777216;
    }

  }
  digitalWrite(ADCCLK, LOW);
  digitalWrite(ADCCS, HIGH); //turn off device
  return adcvalue;
}



//   //set up serial communication, used during debugging to output data to the computer, not used during actual testing
//
// long int total = 0;
// long int average = 0;
//
// digitalWrite(2, LOW);
//
// for (int i=10; i>0; i--){
//   total = total + read_adc(4);
//
//    Serial.println("total");
//  }
//
// average = total/10;
//
// Serial.print("before: ");
// Serial.println(average);
// digitalWrite(2, HIGH);
//
//  for (int j=15; j>0; j--){
//
//    total = 0;
//    average = 0;
//
//    for (int i=10; i>0; i--){
//    total = total + read_adc(4);
//    }
//
//    average = total/10;
//    Serial.println(average);
//    delay(2000);
//
//  }
//
// digitalWrite(2, LOW);
//
// Serial.println("TEST");
// delay(30000);

