# coding: utf-8
from database import DemoData, Instance, User
from sqlalchemy import desc
import logging
import urllib2
import datetime
from demo_exception import *
from demo_mail import DemoMail
import os
import ssl

class Demo():
    def __init__(self, config):
        self.config = config
        self.database = DemoData.get_session(self.config)

        # Security Email
        if self.config.security_type == "email":
            self.mail = DemoMail(
                host=self.config.mail_host,
                port=self.config.mail_port,
                from_mail=self.config.mail_from,
                user=self.config.mail_user,
                password=self.config.mail_password,
                tls=self.config.mail_tls,
            )
        else:
            self.mail = None

        # Security Auth
        if self.config.security_type.startswith('auth_'):
            path = os.path.join(os.path.dirname(__file__), "auth")
            mod_name = self.config.security_type
            auth_mod = __import__(
                'auth.'+mod_name,
                globals(), locals(),
                fromlist=[mod_name]
            )
            auth_class = getattr(auth_mod, Demo.get_class_name(mod_name))
            self.auth = auth_class(self.config.auth)
        else:
            self.auth = False

        # Provider
        path = os.path.join(os.path.dirname(__file__), "provider")
        prov_name = 'prov_'+self.config.provider
        prov_mod = __import__(
            'provider.'+prov_name,
            globals(), locals(),
            fromlist=[prov_name]
        )
        prov_class = getattr(
            prov_mod, Demo.get_class_name(self.config.provider)
        )
        self.provider = prov_class(self.config.provider_data)

    def __del__(self):
        self.database.close()

    @staticmethod
    def get_class_name(mod_name):
        output = ""
        words = mod_name.split("_")
        for word in words:
            output += word.title()
        return output

    def get_type(self, instance_id):
        query = self.database.query(Instance).filter(
            Instance.provider_id == instance_id
        )
        data_instance = query.first()
        return data_instance.image_key

    def get_soft_address(self, instance):
        return self.placeholder_apply(
            self.config.images[self.get_type(instance)]['soft_url'],
            instance)

    def get_dead_time(self, id):
        query = self.database.query(Instance).filter(
            Instance.provider_id == id
        )
        data_instance = query.first()
        return data_instance.get_dead_time()

    def get_life_time(self, id):
        query = self.database.query(Instance).filter(
            Instance.provider_id == id
        )
        data_instance = query.first()
        return data_instance.life_time

    def create_instance(self, image_key, time, token):
        logging.info("Create Instance")
        image = self.config.images[image_key]
        active_instance = self.database_count_active_instance(image_key)

        if self.check_user_own_instance_type(token, image_key):
            raise DemoExceptionUserAlreadyHaveInstanceImage()
        elif 'max_instance' in image\
                and active_instance >= image['max_instance']:
            raise DemoExceptionToMuchInstanceImage()
        else:
            # Add a demand
            database_instance = Instance()
            database_instance.status = 'ASK'
            database_instance.launched_at = datetime.datetime.now()
            database_instance.life_time = 10
            database_instance.image_key = image_key
            database_instance.token = '0'
            self.database.add(database_instance)
            self.database.commit()

            try:
                pool = self.get_pooled_instance_database(image_key)
                if len(pool) > 0:
                    new_instance_id = pool.pop(0)['id']
                else:
                    new_instance_id = self.provider.create_instance(image)

                # If more than max go to max
                life_time = image['time_default']
                if time is not None and 'time_max' in image and\
                        time <= image['time_max']:
                    life_time = time

                self.database_insert_server(
                    new_instance_id, status='CREATED',
                    life_time=life_time,
                    image_key=image_key, token=token,
                    launched_at=datetime.datetime.now()
                )
            finally:
                # Remove the demand even if the provider failed,
                # otherwise the ASK row leaks and eats the quota forever
                self.database.delete(database_instance)
                self.database.commit()

            return new_instance_id

    def create_pool_instance(self, image_key):
        image = self.config.images[image_key]
        new_instance_id = self.provider.create_instance(image)
        self.database_insert_server(
                new_instance_id, status='POOL',
                life_time=0, token=-1,
                image_key=image_key
            )
        return new_instance_id

    def instance_is_up(self, instance_id):
        if self.provider.instance_is_up(instance_id):
            self.database_insert_server(instance_id, 'UP',
                                        ip=self.provider.get_instance_ip(instance_id))
            return True
        return False

    def check_system_up(self, instance_id):
        image = self.config.images[self.get_type(instance_id)]
        if 'check_url' not in image:
            return True
        url = self.placeholder_apply(
            image['check_url'],
            instance_id
        )
        try:
            context = ssl._create_unverified_context()
            code = urllib2.urlopen(url, context=context).getcode()
        except Exception as e:
            logging.exception('Cannot reach instance %s', url)
            return False

        if code == 200:
            self.database_insert_server(instance_id, 'DONE')
            return True
        return False

    # DATABASE #
    def database_insert_server(self, instance_id, status=None,
                               launched_at=None, life_time=None,
                               image_key=None, token=None, ip=None):
        logging.debug('Insert instance %s', instance_id)

        query = self.database.query(Instance).filter(
            Instance.provider_id == instance_id
        )

        if query.count() > 0:
            data_instance = query.first()
        else:
            data_instance = Instance()
            data_instance.launched_at = datetime.datetime.now()

        data_instance.provider_id = instance_id
        data_instance.status = status

        if ip:
            data_instance.ip = ip
        
        if image_key:
            data_instance.image_key = image_key

        # Overwrite launched
        if launched_at is not None:
            data_instance.launched_at = launched_at

        if life_time is not None:
            data_instance.life_time = life_time

        if token is not None:
            data_instance.token = token

        self.database.merge(data_instance)
        self.database.commit()
        return data_instance

    def database_remove_server(self, id):
        logging.info('DELETE instance %s', id)

        # nova
        if self.provider.instance_is_up(id):
            self.provider.remove_instance(id)
        else:
            logging.debug('Instance %s not in cloud', id)

        # database
        query = self.database.query(Instance).filter(
            Instance.provider_id == id
        )
        database_instance = query.first()
        database_instance.status = 'DELETED'
        self.database.merge(database_instance)
        self.database.commit()

    def database_count_active_instance(self, image_key):
        query = self.database.query(Instance).filter(
            Instance.status != 'DELETED',
            Instance.status != 'POOL',
            Instance.image_key == image_key
        )
        logging.debug('%s actives instances for %s', query.count(), image_key)
        return query.count()

    def instance_add_time(self, instance_id, add_time):

        query = self.database.query(Instance).filter(
            Instance.provider_id == instance_id
        )
        data_instance = query.first()

        image = self.config.images[data_instance.image_key]
        if 'time_max' not in image:
            raise DemoExceptionNonUpdatableInstance

        total_time = data_instance.life_time + add_time

        if total_time > image['time_max']:
            total_time = image['time_max']

        data_instance.life_time = total_time
        data_instance.user_alerted = False
        self.database.merge(data_instance)
        self.database.commit()
        return data_instance.life_time

    def instance_set_life_time(self, instance_id, time):

        query = self.database.query(Instance).filter(
            Instance.provider_id == instance_id
        )
        data_instance = query.first()

        data_instance.life_time = time
        data_instance.user_alerted = False
        self.database.merge(data_instance)
        self.database.commit()
        return data_instance.life_time
    # END DATABASE #

    # USER #
    def create_user(self, login=None):
        user = User()
        if login is not None:
            # User already exist ?
            query = self.database.query(User).filter(
                User.login == login
            )
            if query.count() >= 1:
                return query.first()

        user.login = login
        user.generate_token()
        user.last_connection = datetime.datetime.now()

        self.database.merge(user)
        self.database.commit()
        return user
    
    def get_user_by_token(self, token):
        query = self.database.query(User).filter(
            User.token == token
        )
        if query.count() == 0:
            return False
        return query.first()

    def update_slack_identifier(self, token, slack_identifier):
        user = self.get_user_by_token(token)
        if user is False:
            return False
        user.slack_identifier = slack_identifier
        self.database.merge(user)
        self.database.commit()
        return user
    
    def update_user_last_connection(self, login):
        user = self.database.query(User).filter(
            User.login == login
        ).first()
        user.last_connection = datetime.datetime.now()

        self.database.merge(user)
        self.database.commit()

    def check_user_own_instance(self, token,
                                provider_id, raise_exception=True):
        user = self.get_user_by_token(token)
        if self.auth and self.auth.is_admin(user.login):
            return True
        query = self.database.query(Instance).filter(
            Instance.provider_id == provider_id
        )
        instance = query.first()
        if instance is not None and instance.token == token:
            return True

        if raise_exception:
            raise DemoExceptionInvalidOwner()
        else:
            return False

    def detach_instance(self, instance):
        self.database_insert_server(instance, status='DELETED')
        
    def warning_user(self, instance,  messager, deleted=False):
        if instance.user_alerted and not deleted:
            return False
        if instance.token is None:
            return False
        query = self.database.query(User).filter(
            User.token == instance.token
        )
        user = query.first()
        if user is None or user.slack_identifier is None or user.slack_identifier == '':
            return False
        image = self.config.images[instance.image_key]
        message=self.config.user_message.format(instance.ip, image['name'])
        if deleted:
            message = message + self.config.user_message_dead
        else:
            message = message + self.config.user_message_warning.format(self.config.user_alert_delay)
        messager.send_alert(user.slack_identifier, message)
        instance.user_alerted = True
        self.database.merge(instance)
        self.database.commit()
        return True
        
    def check_user_own_instance_type(self, token, image_key):
        query = self.database.query(Instance).filter(
            Instance.image_key == image_key,
            Instance.token == token,
            Instance.status != 'DELETED'
        )
        if query.count() > 0:
            return True
        return False

    def get_user_instance_database(self, token):
        query = self.database.query(Instance).filter(
            Instance.token == token,
        ).order_by(desc(Instance.id))
        logging.debug("%s instances for user %s", query.count(), token)
        info = []
        for instance in query.all():
            info.append({
                'id': instance.provider_id,
                'status': instance.status,
                'type': instance.image_key,
                'launched_at': str(instance.launched_at),
                'life_time': instance.life_time,
                'dead_time': instance.get_dead_time()
            })
        return info

    def get_all_instance_database(self):
        query = self.database.query(Instance, User.login)\
            .join(User, Instance.token == User.token)\
            .order_by(desc(Instance.id))

        info = []
        for instance, login in query.all():
            info.append({
                'id': instance.provider_id,
                'status': instance.status,
                'type': instance.image_key,
                'launched_at': str(instance.launched_at),
                'life_time': instance.life_time,
                'user': login,
                'dead_time': instance.get_dead_time()
            })
        return info

    def get_active_instance_database(self):
        query = self.database.query(Instance, User.login)\
            .join(User, Instance.token == User.token)\
            .filter(Instance.status != 'DELETED')\
            .order_by(desc(Instance.id))

        info = []
        for instance, login in query.all():
            info.append({
                'id': instance.provider_id,
                'status': instance.status,
                'type': instance.image_key,
                'ip': instance.ip,
                'launched_at': str(instance.launched_at),
                'life_time': instance.life_time,
                'user': login,
                'dead_time': instance.get_dead_time()
            })
        return info

    
    def get_pooled_instance_database(self, image_key=None):
        query = self.database.query(Instance)\
            .filter(Instance.status == 'POOL')

        if image_key is not None:
            query = query.filter(Instance.image_key == image_key)

        info = []
        for instance in query.all():
            if instance.ip is None and self.provider.instance_is_up(instance.provider_id):
                instance.ip = self.provider.get_instance_ip(instance.provider_id)
                self.database_insert_server(instance.provider_id, 'POOL',
                                            ip=instance.ip)
            info.append({
                'id': instance.provider_id,
                'status': instance.status,
                'type': instance.image_key,
                'ip': instance.ip,
                'launched_at': str(instance.launched_at),
                'life_time': instance.life_time,
                'dead_time': instance.get_dead_time()
            })
        return info
    # END USER #

    def placeholder_apply(self, param, instance_id):
        ip = self.provider.get_instance_ip(instance_id)
        param = param.replace("%ip%", ip)
        return param
