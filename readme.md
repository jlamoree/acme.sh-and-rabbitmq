# Using acme.sh with RabbitMQ

## Background

I have an internal DNS server on my office LAN that is authoritative for `internal.newbury-park.lamoree.net`. The public internet cannot resolve hostnames in that zone. If I want to use DNS-based verification for Let's Encrypt, I'll need to use a challenge alias. Hosted zones exist in AWS Route 53 for `newbury-park.lamoree.net` and `aws.lamoree.net` and their records can be programmatically managed using the AWS API.

When requesting a certificate, acme.sh does the work of creating a TXT record in `aws.lamoree.net` with the certificate issuer's ACME challenge value. The issuer can verify the challenge using a preexisting CNAME in the `newbury-park.lamoree.net` zone. The result is a certificate issued for `rabbitmq.internal.newbury-park.lamoree.net` without any involvement of my internal DNS infrastructure. The CNAME can remain in place; the TXT record gets deleted automatically.

For some development work, I want to use the issued TLS certificate with RabbitMQ in Docker on my workstation. I'll verify that it's successful with some basic Python programs.

## Download and Setup

Download the gzipped tarball distribution of the desired version from https://github.com/acmesh-official/acme.sh/releases
Perform the following:

```shell
pushd Downloads
tar -zxf acme.sh-3.0.5.tar.gz
pushd acme.sh-3.0.5
./acme.sh --install --force --log --accountemail admin@lamoree.net
popd
rm -rf acme.sh-3.0.5 acme.sh-3.0.5.tar.gz
popd
```


## Create AWS Credentials

Create an AWS IAM user with only the permissions necessary:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "route53:GetHostedZone",
                "route53:ListHostedZones",
                "route53:ListHostedZonesByName",
                "route53:GetHostedZoneCount",
                "route53:GetChange"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "route53:ChangeResourceRecordSets",
                "route53:ListResourceRecordSets"
            ],
            "Resource": [
                "arn:aws:route53:::hostedzone/Z0123123",
                "arn:aws:route53:::hostedzone/Z0ABCDEF"
            ]
        }
    ]
}
```

Save credentials for use when called on schedule.

```shell
mkdir -p "$HOME/.aws/users"
chmod 0700 "$HOME/.aws/users"
touch "$HOME/.aws/users/acme"
chmod 0600 "$HOME/.aws/users/acme"
echo "AKIAEXAMPLEEXAMPLE:secretsecretsecretsecretsecretsecret" > "$HOME/.aws/users/acme"
```


## Prepare a CNAME in Route 53 for challenge alias

A CNAME record needs to be created in the cert zone, pointing to the record that acme.sh will create in the challenge zone.
Specify the `cert_short_hostname` and `cert_zone_qualifier` if desired.

```shell
cert_short_hostname=rabbitmq
cert_zone_qualifier=internal
cert_zone_domain=newbury-park.lamoree.net
challenge_zone_domain=aws.lamoree.net

export AWS_ACCESS_KEY_ID="$(head -n 1 $HOME/.aws/users/acme | cut -d : -f 1)"
export AWS_SECRET_ACCESS_KEY="$(head -n 1 $HOME/.aws/users/acme | cut -d : -f 2)"

if [ -z "${cert_zone_qualifier}" ]; then
  cert_fqdn_hostname="${cert_short_hostname}.${cert_zone_domain}"
  challenge_fqdn_hostname="${cert_short_hostname}.${challenge_zone_domain}"
else
  cert_fqdn_hostname="${cert_short_hostname}.${cert_zone_qualifier}.${cert_zone_domain}"
  challenge_fqdn_hostname="${cert_short_hostname}.${cert_zone_qualifier}.${challenge_zone_domain}"
fi

cert_hosted_zone_path=$(aws route53 list-hosted-zones-by-name --dns-name $cert_zone_domain --query HostedZones[0].Id --output text)
change_json=$(mktemp)
cat <<EOF > $change_json
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "_acme-challenge.${cert_fqdn_hostname}",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "_acme-challenge.${challenge_fqdn_hostname}."
          }
        ]
      }
    }
  ]
}
EOF
aws route53 change-resource-record-sets --hosted-zone-id "${cert_hosted_zone_path##*/}" \
  --change-batch file://$change_json --output text
```


## Issue (or Renew) a Certificate

The challenge value will be created as a TXT record for the CA to verify. To renew a certificate, replace `--issue` with `--renew`.

```shell
cert_short_hostname=rabbitmq
cert_zone_qualifier=internal
cert_zone_domain=newbury-park.lamoree.net
challenge_zone_domain=aws.lamoree.net

export AWS_ACCESS_KEY_ID=$(head -n 1 $HOME/.aws/users/acme | cut -d : -f 1)
export AWS_SECRET_ACCESS_KEY=$(head -n 1 $HOME/.aws/users/acme | cut -d : -f 2)

if [ -z "${cert_zone_qualifier}" ]; then
  cert_fqdn_hostname="${cert_short_hostname}.${cert_zone_domain}"
  challenge_fqdn_hostname="${cert_short_hostname}.${challenge_zone_domain}"
else
  cert_fqdn_hostname="${cert_short_hostname}.${cert_zone_qualifier}.${cert_zone_domain}"
  challenge_fqdn_hostname="${cert_short_hostname}.${cert_zone_qualifier}.${challenge_zone_domain}"
fi

$HOME/.acme.sh/acme.sh --issue --dns dns_aws --server letsencrypt \
  --domain $cert_fqdn_hostname --challenge-alias $challenge_fqdn_hostname
```


## Using the Certificate

Run a RabbitMQ instance using the key generated and TLS certificate issued.

```shell
server_fqdn="rabbitmq.internal.newbury-park.lamoree.net"
acme_cert_home="$HOME/.acme.sh/${server_fqdn}"
rabbitmq_conf_dir=$(mktemp -d)
mkdir "${rabbitmq_conf_dir}/tls"
cp "${acme_cert_home}/ca.cer" "${rabbitmq_conf_dir}/tls/ca.crt"
cp "${acme_cert_home}/${server_fqdn}.cer" "${rabbitmq_conf_dir}/tls/rabbitmq.crt"
cp "${acme_cert_home}/${server_fqdn}.key" "${rabbitmq_conf_dir}/tls/rabbitmq.key"

cat <<EOF > "${rabbitmq_conf_dir}/rabbitmq.conf"
listeners.ssl.default = 5671
ssl_options.cacertfile = /etc/rabbitmq/tls/ca.crt
ssl_options.certfile = /etc/rabbitmq/tls/rabbitmq.crt
ssl_options.keyfile = /etc/rabbitmq/tls/rabbitmq.key
management.tcp.ip = 0.0.0.0
management.ssl.port = 15671
management.ssl.cacertfile = /etc/rabbitmq/tls/ca.crt
management.ssl.certfile = /etc/rabbitmq/tls/rabbitmq.crt
management.ssl.keyfile = /etc/rabbitmq/tls/rabbitmq.key
EOF
docker run --rm -it --hostname rabbitmq --name rabbitmq \
  --volume "${rabbitmq_conf_dir}/rabbitmq.conf":/etc/rabbitmq/rabbitmq.conf:ro \
  --volume "${rabbitmq_conf_dir}/tls":/etc/rabbitmq/tls:ro \
  -p 15671:15671 -p 5671:5671 \
  -p 15672:15672 -p 5672:5672 \
  rabbitmq:3-management
```
