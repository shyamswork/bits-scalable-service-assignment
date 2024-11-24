from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import json
import threading
import pika
import time

# Flask app and database setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@db-order-service:5432/orderdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define the Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(80), nullable=False)

# RabbitMQ Consumer Class
class RabbitMQConsumer:
    def __init__(self, queue_name):
        self.queue_name = queue_name
        self.connection = None
        self.channel = None
        self.is_consuming = False

    def connect(self):
        """Connect to RabbitMQ using SelectConnection (non-blocking)."""
        try:
            print("Connecting to RabbitMQ...")
            parameters = pika.ConnectionParameters(host='rabbitmq')
            self.connection = pika.SelectConnection(
                parameters,
                on_open_callback=self.on_connection_open,
                on_open_error_callback=self.on_connection_open_error,
                on_close_callback=self.on_connection_closed,
            )
            self.is_consuming = True
            print("Starting RabbitMQ ioloop...")
            self.connection.ioloop.start()
        except Exception as e:
            print(f"Error in connect method: {e}")

    def on_connection_open(self, connection):
        """Callback when connection to RabbitMQ is successfully opened."""
        print("Connection to RabbitMQ opened.")
        self.connection.channel(on_open_callback=self.on_channel_open)

    def on_connection_open_error(self, connection, error):
        """Callback when there's an error opening the connection."""
        print(f"Error opening connection: {error}")
        self.is_consuming = False

    def on_connection_closed(self, connection, reason):
        """Callback when connection is closed."""
        print(f"Connection closed: {reason}")
        self.is_consuming = False
        try:
            self.connection.ioloop.stop()
        except Exception:
            pass

    def on_channel_open(self, channel):
        """Callback when channel is successfully opened."""
        print("Channel opened.")
        self.channel = channel
        self.channel.queue_declare(queue=self.queue_name, durable=True, callback=self.on_queue_declared)

    def on_queue_declared(self, method_frame):
        """Callback when queue declaration is complete."""
        print(f"Queue '{self.queue_name}' declared.")
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self.process_message,
            auto_ack=False,  # Manual acknowledgment
        )
        print("Started consuming messages.")

    def process_message(self, channel, method, properties, body):
        """Process messages received from the RabbitMQ queue."""
        try:
            message = json.loads(body)
            print(f"Received message: {message}")

            # Business logic: Add order to the database
            user_id = message.get('user_id')
            product_id = 1
            with app.app_context():
                order = Order(user_id=user_id, product_id=product_id, status='order_created')
                db.session.add(order)
                db.session.commit()
                print("Order created in database.")

            # Acknowledge the message
            channel.basic_ack(delivery_tag=method.delivery_tag)

            # Publish a message to the notification queue
            message['status'] = 'order_created'
            publish_message('notification_queue', message)
            print("Message published to notification_queue.")
        except Exception as e:
            print(f"Error processing message: {e}")
            # Reject and requeue the message
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def stop_consuming(self):
        """Stop consuming messages and close the connection."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            print("RabbitMQ connection closed.")

# Publish messages to RabbitMQ
def publish_message(queue, message):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
        channel = connection.channel()
        channel.queue_declare(queue=queue, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),  # Make message persistent
        )
        connection.close()
        print(f"Published message to queue {queue}: {message}")
    except Exception as e:
        print(f"Error publishing message: {e}")

# Initialize the RabbitMQ consumer
consumer = RabbitMQConsumer(queue_name='order_queue')

@app.route('/process', methods=['GET'])
def start_consumer():
    """Start the RabbitMQ consumer in a separate thread."""
    print("Received request to start consumer.")
    if not consumer.is_consuming:
        print("Starting consumer thread.")
       # thread = threading.Thread(target=consumer.connect, daemon=True)
       # thread.start()
        consumer.connect()
       # print(f"Thread started: {thread.name}")
        return "Consumer started.", 200
    else:
        return "Consumer is already running.", 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    # Retry RabbitMQ connection if it fails initially
    while True:
        try:
            print("Attempting to connect to RabbitMQ...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
            connection.close()
            print("RabbitMQ is reachable. Starting Flask app...")
            break
        except pika.exceptions.AMQPConnectionError as e:
            print(f"RabbitMQ is not reachable. Retrying in 5 seconds... Error: {e}")
            time.sleep(5)
        except Exception as general_error:
            print(f"Unexpected error while connecting to RabbitMQ: {general_error}")
            time.sleep(5)

    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)

