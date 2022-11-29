import pika

cp = pika.ConnectionParameters(host="rabbitmq.internal.newbury-park.lamoree.net")
connection = pika.BlockingConnection(cp)
channel = connection.channel()
channel.queue_declare(queue="hello")
channel.basic_publish(exchange="", routing_key="hello", body=b"A Plain Hello")
print("Message sent")
