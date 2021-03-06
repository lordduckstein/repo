#!/usr/bin/python
# -*- coding: utf-8 -*-

import urllib
import urllib2
import os
import sys
import socket
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs
import time
import datetime
import json
import re

__addon__ = xbmcaddon.Addon()
__addonID__ = __addon__.getAddonInfo('id')
__addonname__ = __addon__.getAddonInfo('name')
__version__ = __addon__.getAddonInfo('version')
__path__ = __addon__.getAddonInfo('path')
__profiles__ = __addon__.getAddonInfo('profile')
__LS__ = __addon__.getLocalizedString

HOME = xbmcgui.Window(10000)
OSD = xbmcgui.Dialog()

__xml__ = xbmc.translatePath('special://skin').split(os.sep)[-2] + '.script-gto-info.xml'

__usertranslations__ = xbmc.translatePath(os.path.join(__profiles__, 'ChannelTranslate.json'))

__prefer_hd__ = True if __addon__.getSetting('prefer_hd').upper() == 'TRUE' else False
__enableinfo__ = True if __addon__.getSetting('enableinfo').upper() == 'TRUE' else False
__pvronly__ = True if __addon__.getSetting('pvronly').upper() == 'TRUE' else False
__preferred_scraper__ = __addon__.getSetting('scraper')

mod = __import__(__preferred_scraper__, locals(), globals(), fromlist=['Scraper'])
Scraper = getattr(mod, 'Scraper')

# Helpers

def getScraperIcon(icon):
    return xbmc.translatePath(os.path.join(__path__, 'resources', 'lib', 'media', icon))

def notifyOSD(header, message, icon=xbmcgui.NOTIFICATION_INFO, disp=4000, enabled=__enableinfo__):
    if enabled:
        OSD.notification(header.encode('utf-8'), message.encode('utf-8'), icon, disp)

def writeLog(message, level=xbmc.LOGDEBUG):
        try:
            xbmc.log('[%s %s]: %s' % (__addonID__, __version__,  message.encode('utf-8')), level)
        except Exception:
            xbmc.log('[%s %s]: %s' % (__addonID__, __version__,  'Fatal: Message could not displayed'), xbmc.LOGERROR)

# End Helpers

if not os.path.isfile(__usertranslations__):
    xbmcvfs.copy(xbmc.translatePath(os.path.join(__path__, 'ChannelTranslate.json')), __usertranslations__)

writeLog('Getting PVR translations from %s' % (__usertranslations__), xbmc.LOGDEBUG)
with open(__usertranslations__, 'r') as transfile:
    ChannelTranslate=transfile.read().rstrip('\n')

infoprops = ['Title', 'Picture', 'Subtitle', 'Description', 'Channel', 'ChannelID', 'Logo', 'Date', 'StartTime', 'RunTime', 'EndTime', 'Genre', 'Cast', 'isRunning', 'isInFuture', 'isInDB', 'dbTitle', 'dbOriginalTitle', 'Fanart', 'dbTrailer', 'dbRating', 'dbUserRating']

# convert HTML Entities to unicode chars

entities = {'&lt;':'<', '&gt;':'>', '&nbsp;':' ', '&amp;':'&', '&quot;':'"'}
tags = {'<br/>':' ', '<hr/>': ''}

def entity2unicode(text):
    for entity in entities.iterkeys():
        text = text.replace(entity, entities[entity])

    # 2nd pass to eliminate html like '<br/>'

    for tag in tags.iterkeys():
        text = text.replace(tag, tags[tag])
    return text

# get remote URL, replace '\' and optional split into css containers

def getUnicodePage(url, container=None):
    try:
        req = urllib2.urlopen(url.encode('utf-8'), timeout=30)
    except UnicodeDecodeError:
        req = urllib2.urlopen(url)

    except ValueError:
        return False
    except urllib2.URLError, e:
        writeLog(str(e.reason), xbmc.LOGERROR)
        return False
    except socket.timeout:
        writeLog('Socket timeout', xbmc.LOGERROR)
        return False

    encoding = 'utf-8'
    if "content-type" in req.headers and "charset=" in req.headers['content-type']:
        encoding=req.headers['content-type'].split('charset=')[-1]
    content = unicode(req.read(), encoding).replace("\\", "")
    if container is None: return content
    return content.split(container)

# get parameter hash, convert into parameter/value pairs, return dictionary

def ParamsToDict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters.split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict

# get used dateformat of kodi

def getDateFormat():
    df = xbmc.getRegion('dateshort')
    tf = xbmc.getRegion('time').split(':')

    try:
        # time format is 12h with am/pm
        return df + ' ' + tf[0][0:2] + ':' + tf[1] + ' ' + tf[2].split()[1]
    except IndexError:
        # time format is 24h with or w/o leading zero
        return df + ' ' + tf[0][0:2] + ':' + tf[1]

# determine and change scraper modules

def changeScraper():
    _scraperdir = xbmc.translatePath(os.path.join(__path__, 'resources', 'lib'))
    _scrapers = []
    _scraperdict = []
    for module in os.listdir(_scraperdir):
        if module in ('__init__.py') or module[-3:] != '.py': continue
        writeLog('Found Scraper Module %s' % (module))
        mod = __import__('resources.lib.%s' % (module[:-3]), locals(), globals(), fromlist=['Scraper'])
        ScraperClass = getattr(mod, 'Scraper')

        if not ScraperClass().enabled: continue

        _scrapers.append(ScraperClass().friendlyname)
        _scraperdict.append({'name': ScraperClass().friendlyname, 'shortname': ScraperClass().shortname, 'module': 'resources.lib.%s' % (module[:-3])})

    _idx = xbmcgui.Dialog().select(__LS__(30111), _scrapers)
    if _idx > -1:
        writeLog('selected scrapermodule is %s' % (_scraperdict[_idx]['module']))
        __addon__.setSetting('scraper', _scraperdict[_idx]['module'])
        __addon__.setSetting('setscraper', _scraperdict[_idx]['shortname'])

# convert datetime string to timestamp with workaround python bug (http://bugs.python.org/issue7980) - Thanks to BJ1

def date2timeStamp(date, format):
    try:
        dtime = datetime.datetime.strptime(date, format)
    except TypeError:
        try:
            dtime = datetime.datetime.fromtimestamp(time.mktime(time.strptime(date, format)))
        except ValueError:
            return False
    except Exception:
        return False
    return int(time.mktime(dtime.timetuple()))

# get pvr channelname, translate from Scraper to pvr channelname if necessary

def channelName2channelId(channelname):
    query = {
            "jsonrpc": "2.0",
            "method": "PVR.GetChannels",
            "params": {"channelgroupid": "alltv"},
            "id": 1
            }
    res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))

    # translate via json if necessary
    translations = json.loads(str(ChannelTranslate))
    for translation in translations:
        for names in translation['name']:
            if channelname.lower() == names.lower():
                writeLog("Translating %s to %s" % (channelname, translation['pvrname']))
                channelname = translation['pvrname']
                break
    
    if 'result' in res and 'channels' in res['result']:
        res = res['result'].get('channels')
        for channels in res:

            # prefer HD Channel if available
            if __prefer_hd__ and  (channelname + " HD").lower() == channels['label'].lower():
                writeLog("GTO found HD priorized channel %s" % (channels['label']))
                return channels['channelid']

            if channelname.lower() == channels['label'].lower():
                writeLog("GTO found channel %s" % (channels['label']))
                return channels['channelid']
    return False

# get pvr channelname by id

def pvrchannelid2channelname(channelid, fallback):
    query = {
            "jsonrpc": "2.0",
            "method": "PVR.GetChannels",
            "params": {"channelgroupid": "alltv"},
            "id": 1
            }
    res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))
    if 'result' in res and 'channels' in res['result']:
        res = res['result'].get('channels')
        for channels in res:
            if channels['channelid'] == channelid:
                writeLog("GTO found id for channel %s" % (channels['label']))
                return channels['label']
    return fallback + '*'

# get pvr channel logo url

def pvrchannelid2logo(channelid, fallback):
    query = {
            "jsonrpc": "2.0",
            "method": "PVR.GetChannelDetails",
            "params": {"channelid": channelid, "properties": ["thumbnail"]},
            "id": 1
            }
    res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))
    if 'result' in res and 'channeldetails' in res['result'] and 'thumbnail' in res['result']['channeldetails']:
        return urllib.unquote_plus(res['result']['channeldetails']['thumbnail']).split('://', 1)[1][:-1]
    else:
        return fallback

def switchToChannel(pvrid):
    writeLog('Switch to channel id %s' % (pvrid))
    query = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "Player.Open",
        "params": {"item": {"channelid": int(pvrid)}}
        }
    res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))
    if 'result' in res and res['result'] == 'OK':
        return True
    else:
        writeLog('Couldn\'t switch to channel id %s' % (pvrid))
    return False


def isInDataBase(title):
    writeLog('Check if \'%s\' is in database' % (title))

    titlepart = re.findall('[:-]', title)
    params = {'isInDB': 'no'}
    query = {"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.GetMovies"}
    rpcQuery = [{"params": {"properties": ["title", "originaltitle", "fanart", "trailer", "rating", "userrating"],
                       "sort": {"method": "label"},
                       "filter": {"field": "title", "operator": "is", "value": title}}},
                {"params": {"properties": ["title", "originaltitle", "fanart", "trailer", "rating", "userrating"],
                       "sort": {"method": "label"},
                       "filter": {"field": "title", "operator": "contains", "value": title}}},
                {"params": {"properties": ["title", "originaltitle", "fanart", "trailer", "rating", "userrating"],
                       "sort": {"method": "label"},
                       "filter": {"field": "title", "operator": "contains", "value": title.replace(' - ', ': ')}}}]
    if len(titlepart) > 0:
        rpcQuery.append({"params": {"properties": ["title", "originaltitle", "fanart", "trailer", "rating", "userrating"],
                       "sort": {"method": "label"},
                       "filter": {"field": "title", "operator": "contains", "value": title.split(titlepart[0])[0].strip()}}})

    for i in range(0, len(rpcQuery) + 1):
        if i == 0:
            writeLog('Try exact matching of search pattern')
            query.update(rpcQuery[i])
        elif i == 1:
            writeLog('No movie(s) with exact pattern found, try fuzzy filters')
            if len(title.split()) < 3:
                writeLog('Word count to small for fuzzy filters')
                return params
        elif i == 2:
            writeLog('No movie(s) with similar pattern found, replacing special chars')
        elif i == 3:
            writeLog('Split title into titleparts')
            if len(titlepart) == 0:
                writeLog('Sorry, splitting isn\'t possible')
                return params
            writeLog('Search for \'%s\'' % (title.split(titlepart[0])[0].strip()))
        else:
            writeLog('Sorry, no matches')
            return params

        query.update(rpcQuery[i])
        res = json.loads(xbmc.executeJSONRPC(json.dumps(query, encoding='utf-8')))
        if 'movies' in res['result']: break

    writeLog('Found %s matches for movie(s) in database, select first' % (len(res['result']['movies'])))
    _fanart = urllib.unquote_plus(res['result']['movies'][0]['fanart']).split('://', 1)[1][:-1]
    _userrating = '0'
    if res['result']['movies'][0]['userrating'] != '': _userrating = res['result']['movies'][0]['userrating']
    params.update({'isInDB': unicode('yes'),
                   'db_title': unicode(res['result']['movies'][0]['title']),
                   'db_originaltitle': unicode(res['result']['movies'][0]['originaltitle']),
                   'db_fanart': unicode(_fanart),
                   'db_trailer': unicode(res['result']['movies'][0]['trailer']),
                   'db_rating': round(float(res['result']['movies'][0]['rating']), 1),
                   'db_userrating': int(_userrating)})
    return params

# clear all info properties (info window) in Home Window

def clearInfoProperties():
    writeLog('clear all info properties (used in info popup)')
    for property in infoprops:
        HOME.clearProperty('GTO.Info.%s' % (property))

def refreshWidget(handle=None, notify=__enableinfo__):

    blobs = int(HOME.getProperty('GTO.blobs') or '0') + 1
    notifyOSD(__LS__(30010), __LS__(30109) % ((Scraper().shortname).decode('utf-8')), icon=getScraperIcon(Scraper().icon), enabled=notify)

    widget = 1
    for i in range(1, blobs, 1):

        writeLog('Processing blob GTO.%s for widget #%s' % (i, widget))
        blob = eval(HOME.getProperty('GTO.%s' % (i)))

        if __pvronly__ and blob['pvrid'] == 'False':
            writeLog("Channel %s is not in PVR, discard entry" % (blob['channel']))
            HOME.setProperty('PVRisReady', 'no')
            continue

        HOME.setProperty('PVRisReady', 'yes')

        wid = xbmcgui.ListItem(label=blob['title'], label2=blob['pvrchannel'])
        wid.setInfo('video', {'title': blob['title'], 'genre': blob['genre'], 'plot': blob['extrainfos'],
                              'cast': blob['cast'].split(','), 'duration': int(blob['runtime'])*60})
        wid.setArt({'thumb': blob['thumb'], 'logo': blob['logo']})

        wid.setProperty('DateTime', blob['datetime'])
        wid.setProperty('StartTime', blob['time'])
        wid.setProperty('EndTime', blob['endtime'])
        wid.setProperty('ChannelID', blob['pvrid'])
        wid.setProperty('BlobID', str(i))
        wid.setProperty('isInDB', blob['isInDB'])
        if blob['isInDB'] == 'yes':
            wid.setProperty('dbTitle', blob['db_title'])
            wid.setInfo('video', {'originaltitle': blob['db_originaltitle'], 'fanart': blob['db_fanart'],
                                  'trailer': blob['db_trailer'], 'rating': blob['db_rating'],
                                  'userrating': blob['db_userrating']})

        if handle is not None: xbmcplugin.addDirectoryItem(handle=handle, url='', listitem=wid)
        widget += 1

    if handle is not None:
        xbmcplugin.endOfDirectory(handle=handle, updateListing=True)

    ts = str(int(time.time()))
    HOME.setProperty('GTO.timestamp', ts)
    xbmc.executebuiltin('Container.Refresh')

def scrapeGTOPage(enabled=__enableinfo__):

    data = Scraper()
    data.err404 = xbmc.translatePath(os.path.join(__path__, 'resources', 'lib', 'media', data.err404))

    notifyOSD(__LS__(30010), __LS__(30018) % ((data.shortname).decode('utf-8')), icon=getScraperIcon(data.icon), enabled=enabled)
    writeLog('Start scraping from %s' % (data.rssurl))

    content = getUnicodePage(data.rssurl, container=data.selector)
    if not content: return

    blobs = int(HOME.getProperty('GTO.blobs') or '0') + 1
    for idx in range(1, blobs, 1):
        HOME.clearProperty('GTO.%s' % (idx))

    idx = 1
    content.pop(0)

    HOME.setProperty('GTO.blobs', '0')
    HOME.setProperty('GTO.provider', data.shortname)
    
    for container in content:

        data.scrapeRSS(container)

        pvrchannelID = channelName2channelId(data.channel)
        logoURL = pvrchannelid2logo(pvrchannelID, data.err404)
        channel = pvrchannelid2channelname(pvrchannelID, data.channel)
        details = getUnicodePage(data.detailURL)

        writeLog('Scraping details from %s' % (data.detailURL))
        data.scrapeDetailPage(details, data.detailselector)

        # calculate runtime

        start = datetime.timedelta(hours=int(data.starttime[0:2]), minutes=int(data.starttime[3:5])).seconds
        end = datetime.timedelta(hours=int(data.endtime[0:2]), minutes=int(data.endtime[3:5])).seconds
        if end < start: end += 86400
        data.runtime = (end - start)/60

        now = datetime.datetime.now()
        now_secs = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
        if end < now_secs:
            writeLog('Broadcast has finished already, discard blob')
            continue
        _st = '%s.%s.%s %s' % (now.day, now.month, now.year, data.starttime)
        try:
            _datetime = time.strftime(getDateFormat(), time.strptime(_st, '%d.%m.%Y %H:%M'))
        except ImportError:
            writeLog('Could not make time conversion, strptime locked', level=xbmc.LOGERROR)
            _datetime = ''

        blob = {
                'title': unicode(entity2unicode(data.title)),
                'thumb': unicode(data.thumb),
                'datetime': unicode(_datetime),
                'time': unicode(data.starttime),
                'runtime': unicode(data.runtime),
                'endtime': unicode(data.endtime),
                'channel': unicode(data.channel),
                'pvrchannel': unicode(channel),
                'pvrid': unicode(pvrchannelID),
                'logo': unicode(logoURL),
                'genre': unicode(entity2unicode(data.genre)),
                'extrainfos': unicode(entity2unicode(data.extrainfos)),
                'popup': unicode(data.detailURL),
                'cast': unicode(entity2unicode(data.cast)),
                'rating': unicode(data.rating)
               }

        # look for similar database entries

        blob.update(isInDataBase(blob['title']))

        writeLog('')
        writeLog('blob:            #%s' % (idx))
        writeLog('Title:           %s' % (blob['title']))
        writeLog('is in Database:  %s' % (blob['isInDB']))
        if blob['isInDB'] == 'yes':
            writeLog('   Title:        %s' % blob['db_title'])
            writeLog('   orig. Title:  %s' % blob['db_originaltitle'])
            writeLog('   Fanart:       %s' % blob['db_fanart'])
            writeLog('   Trailer:      %s' % blob['db_trailer'])
            writeLog('   Rating:       %s' % blob['db_rating'])
            writeLog('   User rating:  %s' % blob['db_userrating'])
        writeLog('Thumb:           %s' % (blob['thumb']))
        writeLog('Date & time:     %s' % (blob['datetime']))
        writeLog('Start time:      %s' % (blob['time']))
        writeLog('End time:        %s' % (blob['endtime']))
        writeLog('Running time:    %s' % (blob['runtime']))
        writeLog('Channel (GTO):   %s' % (blob['channel']))
        writeLog('Channel (PVR):   %s' % (blob['pvrchannel']))
        writeLog('ChannelID (PVR): %s' % (blob['pvrid']))
        writeLog('Channel logo:    %s' % (blob['logo']))
        writeLog('Genre:           %s' % (blob['genre']))
        writeLog('Extrainfos:      %s' % (blob['extrainfos']))
        writeLog('Cast:            %s' % (blob['cast']))
        writeLog('Rating:          %s' % (blob['rating']))
        writeLog('Popup:           %s' % (blob['popup']))
        writeLog('')

        HOME.setProperty('GTO.%s' % (idx), str(blob))
        idx += 1

    ts = str(int(time.time()))
    HOME.setProperty('GTO.blobs', str(idx - 1))
    HOME.setProperty('GTO.timestamp', ts)
    writeLog('%s items scraped and written to blobs @%s' % (idx - 1, ts))
    xbmc.executebuiltin('Container.Refresh')

# Set details to Window (INFO Labels)

def showInfoWindow(blobId, showWindow=True):
    writeLog('Collect and set details to home/info screen for blob #%s' % (blobId or '<unknown>'))

    if blobId is '' or None:
        writeLog('No ID provided', level=xbmc.LOGFATAL)
        return False

    blob = eval(HOME.getProperty('GTO.%s' % (blobId)))

    clearInfoProperties()

    try:
        if blob['pvrid'] != 'False':
            timestamp = date2timeStamp(blob['datetime'], '%d.%m.%Y %H:%M')
            if timestamp >= int(time.time()):
                writeLog('Start time of title \'%s\' is @%s, enable switchtimer button' % (blob['title'], blob['time']))
                HOME.setProperty("GTO.Info.isInFuture", "yes")
            elif timestamp < int(time.time()) < timestamp + 60 * int(blob['runtime']):
                writeLog('Title \'%s\' is currently running, enable switch button' % (blob['title']))
                HOME.setProperty("GTO.Info.isRunning", "yes")
        else:
            writeLog('No PVR Channel available for %s, disable buttons' % (blob['channel']))
    except (ImportError, ValueError):
        writeLog('Could not make time conversion, strptime locked', level=xbmc.LOGERROR)

    HOME.setProperty("GTO.Info.Title", blob['title'])
    HOME.setProperty("GTO.Info.Picture", blob['thumb'])
    HOME.setProperty("GTO.Info.Description", blob['extrainfos'] or __LS__(30140))
    HOME.setProperty("GTO.Info.Channel", blob['pvrchannel'])
    HOME.setProperty("GTO.Info.ChannelID", blob['pvrid'])
    HOME.setProperty("GTO.Info.Logo", blob['logo'])
    HOME.setProperty("GTO.Info.Date", blob['datetime'])
    HOME.setProperty("GTO.Info.StartTime", blob['time'])
    HOME.setProperty("GTO.Info.RunTime", blob['runtime'])
    HOME.setProperty("GTO.Info.EndTime", blob['endtime'])
    HOME.setProperty("GTO.Info.Genre", blob['genre'])
    HOME.setProperty("GTO.Info.Cast", blob['cast'])
    HOME.setProperty("GTO.Info.isInDB", blob['isInDB'])
    if blob['isInDB'] == 'yes':
        HOME.setProperty("GTO.Info.dbTitle", blob['db_title'])
        HOME.setProperty("GTO.Info.dbOriginalTitle", blob['db_originaltitle'])
        HOME.setProperty("GTO.Info.Fanart", blob['db_fanart'])
        HOME.setProperty("GTO.Info.dbTrailer", blob['db_trailer'])
        HOME.setProperty("GTO.Info.dbRating", str(blob['db_rating']))
        HOME.setProperty("GTO.Info.dbUserRating", str(blob['db_userrating']))

    if showWindow:
        Popup = xbmcgui.WindowXMLDialog(__xml__, __path__)
        Popup.doModal()
        del Popup

# _______________________________
#
#           M A I N
# _______________________________

action = None
blob = None
pvrid = None

arguments = sys.argv

if len(arguments) > 1:

    if arguments[0][0:6] == 'plugin':
        writeLog('calling script as plugin source')
        _addonHandle = int(arguments[1])
        arguments.pop(0)
        arguments[1] = arguments[1][1:]

    params = ParamsToDict(arguments[1])
    action = urllib.unquote_plus(params.get('action', ''))
    blob = urllib.unquote_plus(params.get('blob', ''))
    pvrid = urllib.unquote_plus(params.get('pvrid', ''))

    writeLog('provided parameter hash: %s' % (arguments[1]))

    if action == 'scrape':
        scrapeGTOPage()

    elif action == 'getcontent':
        writeLog('Filling widget with handle #%s' % (_addonHandle))
        refreshWidget(handle=_addonHandle, notify=False)

    elif action == 'refresh':
        refreshWidget()

    elif action == 'infopopup':
        showInfoWindow(blob)

    elif action == 'sethomecontent':
        showInfoWindow(blob, showWindow=False)

    elif action == 'switch_channel':
        switchToChannel(pvrid)

    elif action == 'change_scraper':
        changeScraper()
