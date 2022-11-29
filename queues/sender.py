import ssl
import pika

context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context.verify_mode = ssl.CERT_REQUIRED
context.load_verify_locations("/etc/ssl/cert.pem")
cp = pika.ConnectionParameters(host="rabbitmq.internal.newbury-park.lamoree.net",
                               port=5671,
                               ssl_options=pika.SSLOptions(context))

connection = pika.BlockingConnection(cp)
channel = connection.channel()
channel.queue_declare(queue="hello")
channel.basic_publish(exchange="", routing_key="hello", body=b"Hello from Simple Sender")
print("Message sent")
