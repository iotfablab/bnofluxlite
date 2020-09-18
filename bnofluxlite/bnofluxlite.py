import argparse
import json
import logging
import os
import socket
import ssl
import sys
import time
from queue import Queue

from .BNO055 import BNO055

import paho.mqtt.client as mqtt

# Logging Configuration
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

handler = logging.FileHandler('/var/log/bnofluxlite.log')
handler.setLevel(logging.ERROR)

formatter = logging.Formatter('%(asctime)s-%(name)s-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


CONFIG = dict()
DEVICE_NAME = ''
DEVICE_ID = ''
INFLUX_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def on_connect(mqttc, obj, flags, rc):
    """MQTT Callback Function upon connecting to MQTT Broker"""
    if rc == 0:
        logger.debug("MQTT CONNECT rc: " + str(rc))
        logger.info("Succesfully Connected to MQTT Broker")


def on_publish(mqttc, obj, mid):
    """MQTT Callback Function upon publishing to MQTT Broker"""
    logger.debug("MQTT PUBLISH: mid: " + str(mid))


def on_disconnect(mqttc, obj, rc):
    if rc == 0:
        logger.debug("MQTT DISCONNECTED: rc: " + str(rc))
        logger.debug("Disconnected Successfully from MQTT Broker")


def setup_mqtt_client(mqtt_conf, mqtt_client):
    """Configure MQTT Client based on Configuration"""

    if mqtt_conf['TLS']['enable']:
        logger.info("TLS Setup for Broker")
        logger.info("checking TLS_Version")
        tls = mqtt_conf['TLS']['tls_version']
        if tls == 'tlsv1.2':
             tlsVersion = ssl.PROTOCOL_TLSv1_2
        elif tls == "tlsv1.1":
            tlsVersion = ssl.PROTOCOL_TLSv1_1
        elif tls == "tlsv1":
            tlsVersion = ssl.PROTOCOL_TLSv1
        else:
            logger.info("Unknown TLS version - ignoring")
            tlsVersion = None
        if not mqtt_conf['TLS']['insecure']:

            logger.info("Searching for Certificates in certdir")
            CERTS_DIR = mqtt_conf['TLS']['certs']['certdir']
            if os.path.isdir(CERTS_DIR):
                logger.info("certdir exists")
                CA_CERT_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['cafile'])
                CERT_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['certfile'])
                KEY_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['keyfile'])

                mqtt_client.tls_set(ca_certs=CA_CERT_FILE, certfile=CERT_FILE, keyfile=KEY_FILE, cert_reqs=ssl.CERT_REQUIRED, tls_version=tlsVersion)
            else:
                logger.error("certdir does not exist.. check path")
                sys.exit()
        else:
            mqtt_client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=tlsVersion)
            mqtt_client.tls_insecure_set(True)
    
    if mqtt_conf['username'] and mqtt_conf['password']:
        logger.info("setting username and password for Broker")
        mqtt_client.username_pw_set(mqtt_conf['username'], mqtt_conf['password'])
    
    return mqtt_client


def send_data(payloads, mqtt_client):
    """Publish IMU Values to MQTT Broker + InfluxDB insert"""
    global CONFIG
    global DEVICE_ID, DEVICE_NAME
    global INFLUX_SOCKET
    while not payloads.empty():
        for topic in CONFIG['imu']['topics']:
            data =  ''.join(list(payloads.queue))
            payloads.queue.clear()
            topic_to_publish = DEVICE_NAME + '/' + DEVICE_ID + '/' + topic
            logger.debug(data)
            mqtt_client.publish(topic_to_publish, data, qos=1)
            INFLUX_SOCKET.sendto(data.encode('utf-8'), (CONFIG['influx']['host'], CONFIG['imu']['udp_port']))


def read_from_imu(i2c_port, updaterate, mqttc):
    """Read from BNO055 Sensor using I2C Port and push data into payload Queue"""
    logger.info(f'Starting to Read BNO values on {i2c_port} every {updaterate}s')
    queue_capacity = 1 / updaterate
    payload_q = Queue(maxsize=queue_capacity)
    logger.debug(f'Setting Queue Capacity of {queue_capacity} equal to Sampling rate')
    sensor_bno = BNO055(i2c_bus_port=i2c_port)
    if sensor_bno.begin() is not True:
        raise ValueError('Initialization Failure for BNO055')
        sys.exit(1)
    time.sleep(1)
    sensor_bno.setExternalCrystalUse(True)
    time.sleep(2)
    logger.info('Reading BNO055 Sensor Data')

    mqttc.loop_start()

    while 1:
        try:
            lx, ly, lz = sensor_bno.getVector(BNO055.VECTOR_LINEARACCEL)
            payload_q.put_nowait(f'acceleration,type=linear,src=imu x={lx},y={ly},z={lz} {time.time_ns()}\n')
            logger.debug('linear acc.: x:{}, y:{}, z:{}'.format(lx, ly, lz))

            gX, gY, gZ = sensor_bno.getVector(BNO055.VECTOR_GRAVITY)
            payload_q.put_nowait(f'acceleration,type=gravity,src=imu x={gX},y={gY},z={gZ} {time.time_ns()}\n')
            logger.debug('gravity: x:{}, y:{}, z:{}'.format(gX, gY, gZ))

            yaw, roll, pitch = sensor_bno.getVector(BNO055.VECTOR_EULER)
            payload_q.put_nowait(f'orientation,type=euler,src=imu yaw={yaw},pitch={pitch},roll={roll} {time.time_ns()}\n')
            logger.debug('euler: yaw:{}, pitch:{}, roll:{}'.format(yaw, pitch, roll))

            time.sleep(updaterate)
            
            if payload_q.full():
                send_data(payload_q, mqttc)

        except Exception as imu_e:
            logger.exception(f'Error while reading IMU data: {imu_e}')
            break
        except KeyboardInterrupt:
            logger.exception('CTRL+C pressed')
            break
    
    logger.info("cleaning up queue, closing connections")
    if not payload_q.empty():
        payload_q.queue.clear()
    mqttc.loop_stop()
    mqttc.disconnect()
    sys.exit()


def parse_arguments():
    """Arguments to run the script"""
    parser = argparse.ArgumentParser(description='CLI to obtain BNO055 data and save them to InfluxDBv1.x and Publish them to MQTT')
    parser.add_argument('--config', '-c', required=True, help='JSON Configuration File for bnofluxlite CLI')
    return parser.parse_args()


def main():
    """Initialization"""
    args = parse_arguments()
    if not os.path.isfile(args.config):
        logger.error("configuration file not readable. Check path to configuration file")
        sys.exit()

    global CONFIG
    with open(args.config, 'r') as config_file:
        CONFIG = json.load(config_file)
    # print(CONFIG)

    # MQTT Client Configuration
    global DEVICE_NAME, DEVICE_ID
    DEVICE_NAME = CONFIG['device']['name']
    DEVICE_ID = CONFIG['device']['ID']
    MQTT_CONF = CONFIG['mqtt']

    mqttc = mqtt.Client(client_id=f'{DEVICE_NAME}/{DEVICE_ID}-IMU')
    mqttc = setup_mqtt_client(MQTT_CONF, mqttc)

    mqttc.on_connect = on_connect
    mqttc.on_publish = on_publish
    mqttc.on_disconnect = on_disconnect

    mqttc.connect(CONFIG['mqtt']['broker'], CONFIG['mqtt']['port'])

    logger.info('Connecting to IMU (BNO055) Device')
    I2C_PORT = CONFIG['imu']['i2cPort']
    I2C_UPDATERATE = CONFIG['imu']['i2cPort']
    logger.debug(f'Device @i2c-{I2C_PORT} with update rate={I2C_UPDATERATE}')

    read_from_imu(I2C_PORT, I2C_UPDATERATE, mqttc)


if __name__ == "__main__":
    main()