from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import pika, json

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@db-user-service:5432/userdb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

# User Workflow Log model
class UserLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(80), nullable=False)

# RabbitMQ publish function
def publish_message(queue, message):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    
    # Declare a durable queue
    channel.queue_declare(queue=queue, durable=True)
    
    # Publish a persistent message
    channel.basic_publish(
        exchange='',
        routing_key=queue,
        body=json.dumps(message),
        properties=pika.BasicProperties(
            delivery_mode=2  # Make the message persistent
        )
    )
    connection.close()


@app.route('/users', methods=['POST'])
def create_user():
    """Endpoint to create a user."""
    data = request.json
    name = data.get('name')
    email = data.get('email')

    if not name or not email:
        return jsonify({'error': 'Name and email are required'}), 400

    # Add user to the database
    new_user = User(name=name, email=email)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': f'User {name} created successfully!', 'user_id': new_user.id}), 201

@app.route('/start_workflow/<int:user_id>', methods=['POST'])
def start_workflow(user_id):
    """Start the workflow for a user."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': f'User with ID {user_id} not found'}), 404

    # Log the start of the workflow
    log = UserLog(user_id=user_id, status='workflow_started')
    db.session.add(log)
    db.session.commit()

    # Publish workflow initiation to RabbitMQ
    message = {'user_id': user_id, 'status': 'workflow_started'}
    publish_message('order_queue', message)

    return jsonify({'message': f'Workflow started for user {user.name}', 'user_id': user_id}), 200

@app.route('/users', methods=['GET'])
def list_users():
    """List all users."""
    users = User.query.all()
    user_list = [{'id': user.id, 'name': user.name, 'email': user.email} for user in users]
    return jsonify(user_list), 200

if __name__ == '__main__':
    # Wrap database table creation in a valid application context
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
