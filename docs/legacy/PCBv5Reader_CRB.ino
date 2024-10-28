//
// Serial communication parameters
//

//#define RF69_COMPAT 1  //This is for backward compatibility with the RF12 drivers. New Boards as of at least 2018 use the RFM69, rather than the RF12. for old boards, omit this line of code
#include <JeeLib.h>
#include <avr/sleep.h>
#include <stdarg.h>
void printHex(char *fmt, ... )
{
  char tmp[128]; // resulting string limited to 128 chars
  va_list args;
  va_start (args, fmt );
  vsnprintf(tmp, 128, fmt, args);
  va_end (args);
  Serial.print(tmp);
}

static const unsigned int serial_baud = 9600;
static const char TERMCHAR = 0x0A; // New line: '\n'
// 2 ADC readings and a termination character
static const unsigned int buffer_size = 5 * sizeof(unsigned long) + sizeof(char);

struct {
  long int start;   // time byte sent
  long int later;   // how long we had to wait for packet to come in
} payload;

typedef struct {
  char r1;
  char r2;
  char r3;
  char r4;
} cflags;

//
// Program behavior parameters
//
static const unsigned int  ms_delay =    1000;
static const unsigned long ADC_mask =    0x00FFFFFF;
static const unsigned char byte_mask =   0xFF;
static const unsigned char byte_offset = 1 << 8;
static const unsigned long random_max =  0x01000000;
static const unsigned long random_min =  0x0;
static char Flagbuffer;



static cflags FLAGS;
static size_t BufferFull;
static int hascmd;
static bool ackconf;
static bool confirmed;
static int counter;
static int ENABLE;


void setup()
{
  Serial.begin(serial_baud);
  rf12_initialize(11, RF12_433MHZ, 20); // Where we can change the radio freq and the id  433,915

  Serial.setTimeout(500); //1000


  FLAGS.r1 = '0';
  FLAGS.r2 = '0';
  FLAGS.r3 = '0';
  FLAGS.r4 = '2';


  ENABLE = 0;
  //Serial.println("Setup Complete");
}

int measurements;

void loop() {
  //Serial.println("running loop");
  if (Serial.available() > 0) {
    //Serial.println("Reading Serial Port");
    //delay(20);
    while (Serial.available()) {
      Flagbuffer = Serial.read();
      //Serial.println(Flagbuffer);
      if (Flagbuffer == 's') {

        Flagbuffer = Serial.read();
        FLAGS.r1 = Flagbuffer;
        Flagbuffer = Serial.read();
        FLAGS.r2 = Flagbuffer;
        Flagbuffer = Serial.read();
        FLAGS.r3 = Flagbuffer;
        Flagbuffer = Serial.read();
        FLAGS.r4 = Flagbuffer;
        //Serial.println(i);
        //Serial.println(FLAGS[i]);

        //FLAGS[0]: 0/1: allows "wait for user" loop to run within centrifuge
        //FLAGS[1]: 0/1: 1 allows centrifuge to take a reading.
        //FLAGS[2]: 0/1: 1 implies valid to transmit other values in FLAGS

      }
    }
  }
  counter = 0;
  ackconf = false;
  while ((counter < 50) && !ackconf) {
    counter++;
    if (rf12_recvDone() && rf12_crc == 0) {
      //Serial.println("Reading Data");
      measurements = 9;
      long int readingArray[measurements];
      for (int i = 0; i < measurements; i++) {
        readingArray[i] = process_reading(i);
      }

      //First Check what kind of Transmission this was:

      if (RF12_WANTS_ACK) {
        //Serial.println("Wants Ack");
        while (!ackconf) {
          if (rf12_canSend()) {
            rf12_sendStart(RF12_ACK_REPLY, &FLAGS, sizeof FLAGS);
            rf12_sendWait(1);
            ackconf = true;
          } else {
            delay(20);
            rf12_recvDone();
            //Serial.println("Waiting to Acknowledge");
          }
        }



        if (FLAGS.r1 == '1') {
          ENABLE = 1;
          FLAGS.r3 = '0'; //Reset the 'valid to transmit' Flag
        }

      }

      for (int j = 0; j < measurements; j++) {
        printHex("%08X", readingArray[j]);
      }
      Serial.println(" ");
      Serial.flush();
      delay(20);

    }
  }
  if ((FLAGS.r3 == '1') && (ENABLE == 1)) {
    hascmd = 1;
    confirmed = 0;
    counter = 0;
    while ((hascmd == 1 || confirmed == 0) && (counter < 500)) {
      if (hascmd == 0) {
        payload.later = (long int) millis() - payload.start;
        if (rf12_recvDone() && rf12_crc == 0) {
          confirmed = 1;
          FLAGS.r3 = '0';
          if (FLAGS.r1 == '0') {
            ENABLE = 0;
          }
          //Serial.println("Ack. recvd.");
        }
        else if (payload.later > 1500) {
          //Serial.println("No Ack., resending.");
          hascmd = 1;
        }
      }else if (hascmd == 1) {
        if (rf12_canSend()) {
          hascmd = 0;
          counter++;
          //Serial.println("Sending Command");
          rf12_sendStart(RF12_HDR_ACK, &FLAGS, sizeof FLAGS);
          rf12_sendWait(10);
          payload.start = millis();
        } else {
          delay(500);
          rf12_recvDone();
          //Serial.println("rf12 can't send, waiting.");
        }
      }
    }
  }
  delay(ms_delay);
}

long int process_reading(int readNum) {
  long int reading = 0;
  reading |= rf12_data[readNum * 4 + 3];
  reading <<= 8;
  reading |= rf12_data[readNum * 4 + 2];
  reading <<= 8;
  reading |= rf12_data[readNum * 4 + 1];
  reading <<= 8;
  reading |= rf12_data[readNum * 4 + 0];
  reading &= ADC_mask;
  if (reading < 0) {
    reading = 0;
  }
  return reading;
}
