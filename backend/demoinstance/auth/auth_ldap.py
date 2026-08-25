# coding=utf-8
from auth import DemoAuth
import ldap


class AuthLdap(DemoAuth):
    def __init__(self, config):
        self.host = config['host']
        self.bind_user = config['bind_user']
        self.bind_password = config['bind_password']
        self.search_base = config['search_base']
        self.login_attribute = config['login_attribute']
        self.admin = []
        if 'admin' in config:
            self.admin = config['admin'].split(',')

    def check_auth(self, user, password):
        try:
            ld = ldap.initialize(self.host)
            ld.simple_bind_s(self.bind_user, self.bind_password)
            search_filter = self.login_attribute+"="+user
            res = ld.search_s(
                self.search_base,
                ldap.SCOPE_SUBTREE,
                search_filter
            )
            ld.unbind_s()
        except ldap.INVALID_CREDENTIALS as e:
            return False

        if len(res) > 1:
            raise Exception("Too many users returned")
        if len(res) < 1:
            return False

        dn, attributes = res[0]
        if not self.__try_bind(dn, password):
            return False
        return user

    def is_admin(self, user):
        if user in self.admin:
            return True
        return False

    def __try_bind(self, dn, password):
        ld = ldap.initialize(self.host)
        try:
            ld.simple_bind_s(dn, password)
            whoami = ld.whoami_s()
            ld.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            return False

        if whoami is None:
            return False
        return True
