import logging

from samba.gpclass import get_dc_hostname
from samba.netcmd.common import netcmd_get_domain_infos_via_cldap
import samba.gpo
import pysss_nss_idmap

from storage import cache_factory

def get_gpo_list(dc_hostname, creds, lp, user):
    gpos = []
    ads = samba.gpo.ADS_STRUCT(dc_hostname, lp, creds)
    if ads.connect():
        #gpos = ads.get_gpo_list(creds.get_username())
        gpos = ads.get_gpo_list(user)
    logging.info('Got GPO list for {}:'.format(user))
    for gpo in gpos:
        # These setters are taken from libgpo/pygpo.c
        # print(gpo.ds_path) # LDAP entry
        logging.info('{} ({})'.format(gpo.display_name, gpo.name))
    logging.info('------')
    return gpos

def select_dc(lp, creds, dc):
    try:
        samba_dc = get_dc_hostname(creds, lp)

        if samba_dc != dc and dc != None:
            logging.debug('Samba DC setting is {} and is overwritten by user setting {}'.format(samba_dc, dc))
            return dc
        return samba_dc
    except:
        logging.error('Unable to determine DC hostname')
    return None

def wbinfo_getsid(domain, user):
    '''
    Get SID using wbinfo
    '''
    # This part works only on client
    username = '{}\\{}'.format(domain.upper(), user)
    sid = pysss_nss_idmap.getsidbyname(username)

    if username in sid:
        return sid[username]['sid']

    # This part works only on DC
    wbinfo_cmd = ['wbinfo', '-n', username]
    output = subprocess.check_output(wbinfo_cmd)
    sid = output.split()[0].decode('utf-8')

    return sid


def get_domain_name(lp, creds, dc):
    '''
    Get current Active Directory domain name
    '''
    try:
        # Get CLDAP record about domain
        # Look and python/samba/netcmd/domain.py for more examples
        res = netcmd_get_domain_infos_via_cldap(lp, None, dc)
        logging.info('Found domain via CLDAP: {}'.format(res.dns_domain))

        return res.dns_domain
    except:
        logging.error('Unable to retrieve domain name via CLDAP query')
    return None

def get_sid(domain, username):
    '''
    Lookup SID not only using wbinfo or sssd but also using own cache
    '''
    cached_sids = cache_factory('sid_cache')
    domain_username = '{}\\{}'.format(domain, username)
    sid = 'local-{}'.format(username)
    sid = cached_sids.get_default(domain_username, sid)

    try:
        sid = wbinfo_getsid(domain, username)
    except:
        sid = 'local-{}'.format(username)
        logging.warning('Error getting SID using wbinfo, will use cached SID: {}'.format(sid))

    logging.debug('Working with SID: {}'.format(sid))

    cached_sids.store(domain_username, sid)

    return sid

def expand_windows_var(text, username):
    '''
    Scan the line for percent-encoded variables and expand them.
    '''
    variables = dict()
    variables['HOME'] = get_homedir(username)
    variables['SystemRoot'] = ''
    variables['DesktopDir'] = '{}/Desktop'.format(variables['HOME'])
    variables['StartMenuDir'] = ''

    result = text
    for var in variables.keys():
        result = result.replace('%{}%'.format(var), variables[var])

    return result

