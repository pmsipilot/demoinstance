FROM ubuntu:16.04
LABEL maintainer="industrialisation@ospi.fr"

RUN apt-get update && apt-get install -y git python python-dev\
 python-pip mysql-client libmysqlclient-dev nodejs npm\
  libldap2-dev libsasl2-dev libssl-dev nginx supervisor
RUN ln -s /usr/bin/nodejs /usr/bin/node

RUN rm -rf /etc/nginx/sites-available/* /etc/nginx/sites-enabled/*

COPY ./ressources/nginx/nginx-server /etc/nginx/sites-available/default
RUN ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
RUN ln -sf /dev/stdout /var/log/nginx/access.log
RUN ln -sf /dev/stderr /var/log/nginx/error.log


RUN mkdir -p /etc/demoinstance/instance_image/
RUN mkdir /opt/demoinstance
COPY ./ /opt/demoinstance

WORKDIR /opt/demoinstance/frontend
RUN npm install
RUN node_modules/gulp/bin/gulp.js


WORKDIR /opt/demoinstance/backend/
RUN pip install --upgrade "pip==20.3.4"
RUN pip install --upgrade setuptools
# python-novaclient 7.1.x ships with the OpenStack Ocata release and only
# declares open lower bounds on its dependencies
# (keystoneauth1>=2.18, oslo.*, ...): without a cap, pip resolves them to
# modern versions that dropped Python 2. The Ocata upper-constraints file
# caps every transitive dependency to the exact versions tested by the
# Ocata CI alongside novaclient 7.1.x. The ocata-eol tag is immutable, so
# the build stays reproducible.
RUN python -m pip install \
    -c https://opendev.org/openstack/requirements/raw/ocata-eol/upper-constraints.txt \
    "python-novaclient==7.1.0"

# Non-OpenStack dependencies, deliberately installed outside the Ocata
# constraints: slackclient 1.3.1 requires a newer requests than the Ocata
# pin, and requests 2.27.1 is the last Python 2 compatible release.
RUN python -m pip install \
    "slackclient==1.3.1" \
    "python-ldap==3.3.1" \
    MySQL-python \
    "sqlalchemy==1.3.24" \
    "requests==2.27.1"

RUN python -m pip install --no-deps .
# RUN python setup.py install

COPY ./ressources/supervisor/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]

EXPOSE 8080
