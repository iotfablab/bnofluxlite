from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()


setup(name='bnofluxlite',
    version='0.0.1',
    description='CLI to parse BNO055 IMU data and publish them via MQTT and store into InfluxDB',
    long_description=readme(),
    author='Shan Desai',
    author_email='des@biba.uni-bremen.de',
    license='MIT',
    packages=['bnofluxlite'],
    scripts=['bin/bnofluxlite', 'bin/calibrate'],
    install_requires=[
        'paho-mqtt'
    ],
    include_data_package=True,
    zip_safe=False)