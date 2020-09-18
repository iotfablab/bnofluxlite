# gpsfluxlite

A lighter version of [`bnoflux`](https://github.com/iotfablab/bnoflux) without the usage of `influxdb-python`.

## Features

- Send data to InfluxDB on a hardware using UDP Socket directly
- Provide TLS settings for connecting to a Secure MQTT Broker
- Use a fixed length queue to store the incoming RMC Co-ordinates in Line Protocol Format and send them to `DEVICE_NAME/DEVICE_ID/imu` topic
  with `QoS=1`
- Based on the updaterate in seconds the sampling rate determines the queue capacity (sampling rate = 1 / update rate) and publishes data


### Secure MQTT Configuration

Followig sample configuration for using a Secure MQTT Broker with Certificates. Use `insecure: true` to not use certificates.

```json
"mqtt": {
      "broker": "secure_broker",
      "port": 8883,
      "username": null,
      "password": null,
      "TLS": {
          "enable": true,
          "insecure": false,
          "tls_version": "tlsv1.2",
          "certs": {
            "certdir": "/etc/ssl/certs/mqtt",
            "cafile": "ca.crt",
            "certfile": "mqtt-client.crt",
            "keyfile": "mqtt-client.key"
          }
      }
    }
```

### InfluxDB UDP Configuration

Sample configuration for `influxdb.conf`

```toml
[[udp]]
  enabled = true
  bind-address = ":8095"
  database = "IoTSink"
  precision = "n"
```