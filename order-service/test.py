import pika
try:
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    print("RabbitMQ is reachable.")
    connection.close()
except pika.exceptions.AMQPConnectionError as e:
    print(f"RabbitMQ connection error: {e}")
