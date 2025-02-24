# Actors

- client: publish message to server, subscribe to message topics
  - does not have an address, can self-identify in their published messages
  - does have an identifier, which it sends during connection
- server: receive messages from clients, dispatch messages to subscribers
  - creates the $SYS topic which publishes information about the broker
  - standard version uses TCP/IP on port 1883
  - if no one is subscribed to a topic, the broker discards those messages
- topic: identifier on a message to support publish/subscribe
  - structured in a hierarchy using the forward slash /
  - only exists if a client has subscribed to it, or a broker has a retained or last will messages stored for that topic

# Connectivity

- Most MQTT clients will connect to the broker and remain connected even if they aren’t sending data.
- Connections are acknowledged by the broker using a Connection acknowledgement message.
- MQTT clients publish a keep-alive message at regular intervals (usually 60 seconds) which tells the broker that the client is still connected
- If you attempt to connect to an MQTT broker with the same name as an existing client then the existing client connection is dropped.
- A client can specify a last will message for each topic from the broker to notify a subscriber that the publisher is unavailable due to network outage

## Bring-up flow

--> Connect(my_identifer)
<-- CONNACK
--> Subscribe(topic, QoS)
<-- SUBACK
--> Publish(message, topic, QoS, is_retained)
<-- PUBACK

## QoS controls whether and how messages are retained by broker for glitchy clients
- QoS 0 - Default and doesn’t guarantee message delivery.
- QoS 1 - Guarantees message delivery but could get duplicates.
- QoS 2 - Guarantees message delivery with no duplicates.

# Topic and payload design patterns

- Separate command and response topics using a prefix e.g command/ and response/
- Include routing information in the topic structure
- subscribe to all topics with '#'
- subscribe to all $SYS topics with '$SYS/#'
- Ensure MQTT topic levels structure follows a general to specific pattern. As topic scheme flows left to right, the topic levels flow general to specific.
- Include any relevant routing information in the MQTT topic. Relevant routing information includes, but is not limited to, the IoT application identifier, any groups the device may be a part of, such as installed location, and the unique identity of your IoT device.
- Prefix your MQTT topics to distinguish data topics from command topics. Make sure that your MQTT topics do not overlap between commands and data messages.
- Include additional contextual information about a specific message in the payload of the MQTT message. This contextual information includes, but is not limited to, a session identifier, the requestor identifier, logging information, or the return topic on which a device is expecting to receive a response.
- Never allow a device to subscribe to all topics using #
- MQTT topics for command requests: cmd/<application>/<context>/<destination-id>/<req-type>
- MQTT topic structure for responding to commands: cmd/<application>/<context>/<destination-id>/<res-type>
- generate a schema for message payloads
  - transaction-id -- unique for each request-response
  - response-topic
- base topic/cmnd/device_id/command
- base topic/response/device_id
- base topic/response/device_id/result
- base topic/status/device_id/state
- base topic/status/device_id/info
- base topic/connected/device_id
- protocol_prefix / src_id / dest_id / message_id / extra_properties
  - https://stackoverflow.com/a/48414867

# Windows broker

- https://mosquitto.org/download/
- https://mosquitto.org/documentation/

## Client

- mosquitto_sub
  - https://mosquitto.org/man/mosquitto_sub-1.html
  --disable-clean-session  --id CLIENT_ID
  --qos LEVEL
  --topic TOPIC
  --will-payload ANNOUNCEMENT  --will-topic TOPIC  --will-qos LEVEL
  --will-retain MESSAGE  --will-topic TOPIC  --will-qos LEVEL
  -F %J
- mosquitto_pub
  - https://mosquitto.org/man/mosquitto_pub-1.html
  --disable-clean-session  --id CLIENT_ID
  --message MESSAGE
  --qos LEVEL
  --retain
  --topic TOPIC
  --will-payload ANNOUNCEMENT  --will-topic TOPIC  --will-qos LEVEL
  --will-retain MESSAGE  --will-topic TOPIC  --will-qos LEVEL

## Broker

- mosquitto --config-file PATH --daemon --port PORT
  - https://mosquitto.org/man/mosquitto-8.html
  - https://github.com/eclipse-mosquitto/mosquitto/blob/master/ChangeLog.txt#L651
- mosquitto.conf
  - https://mosquitto.org/man/mosquitto-conf-5.html
- $SYS topics
  - "$SYS/broker/bytes/sent"
  - "$SYS/broker/load/bytes/received/15min"
  - "$SYS/broker/load/bytes/received/1min"
  - "$SYS/broker/load/bytes/received/5min"
  - "$SYS/broker/load/bytes/sent/15min"
  - "$SYS/broker/load/bytes/sent/1min"
  - "$SYS/broker/load/bytes/sent/5min"
  - "$SYS/broker/load/connections/1min"
  - "$SYS/broker/load/connections/5min"
  - "$SYS/broker/load/messages/received/1min"
  - "$SYS/broker/load/messages/received/5min"
  - "$SYS/broker/load/messages/sent/15min"
  - "$SYS/broker/load/messages/sent/1min"
  - "$SYS/broker/load/messages/sent/5min"
  - "$SYS/broker/load/publish/sent/15min"
  - "$SYS/broker/load/publish/sent/1min"
  - "$SYS/broker/load/publish/sent/5min"
  - "$SYS/broker/load/sockets/1min"
  - "$SYS/broker/load/sockets/5min"
  - "$SYS/broker/messages/sent"
  - "$SYS/broker/publish/bytes/sent"
  - "$SYS/broker/publish/messages/sent"
  - "$SYS/broker/store/messages/bytes"
  - "$SYS/broker/uptime"

All lines with a # as the very first character are treated as a comment
Configuration lines start with a variable name. The variable value is separated from the name by a single space.

allow_anonymous false
allow_zero_length_clientid false
autosave_interval SECONDS
connection_messages true
log_dest topic
log_timestamp_format %Y-%m-%dT%H:%M:%S
max_inflight_messages 1

## Experiments

- paho-mqtt
  - 🅰️ https://github.com/empicano/aiomqtt
- 🅱️ https://github.com/wialon/gmqtt
  - https://github.com/sabuhish/fastapi-mqtt
- https://hbmqtt.readthedocs.io/en/latest/references/index.html
  - https://github.com/Yakifo/amqtt
