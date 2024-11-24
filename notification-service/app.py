import pika, json
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@db-notification-service:5432/notificationdb'
db = SQLAlchemy(app)

# Define the Notification model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(255), nullable=False)

# Function to process messages from RabbitMQ
def process_message(ch, method, properties, body):
    message = json.loads(body)
    print(f"Notification Service received: {message}")
    user_id = message.get('user_id')
    notification_message = f"Order workflow completed for user {user_id}"

    # Save the notification to the database
    with app.app_context():
        notification = Notification(user_id=user_id, message=notification_message)
        db.session.add(notification)
        db.session.commit()

    print(f"Notification sent for user_id {user_id}: {notification_message}")

@app.route('/process', methods=['GET'])
def consume():
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()

    # Declare the queue with the same properties
    # Ensure 'durable=True' to match the previously created queue
    channel.queue_declare(queue='notification_queue', durable=True)

    channel.basic_consume(queue='notification_queue', on_message_callback=process_message, auto_ack=True)
    print("Notification Service is consuming messages.")
    channel.start_consuming()

if __name__ == '__main__':
    # Ensure the tables are created before starting the app
    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', port=5000, debug=True)
