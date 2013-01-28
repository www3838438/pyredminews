# PyRedmineWS - Python Redmine Web Services
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

# This file contains the under-the-hood functions and lower-level interactions.


import urllib
import urllib2
import json

class RedmineError(StandardError):
    pass


class Redmine_Item(object):
    '''Base class used for all items returned from Redmine.'''
    # Data hints
    id = None

    # List out the attributes that aren't user-settable
    _protected_attr = ['id']

    _type = None
    
    # Tracks changed attributes on this object.  __init__ sets it to {} to kick off tracking.
    _changes = None

    # These tags are remapped from tag to tag_id when creating or saving
    _remap_to_id = []

    _query_path = ''
    _query_container = ''
    _item_path = ''
    _item_new_path = ''
    
    @classmethod
    def _get_type(cls):
        '''Returns the object type string.
        This string is required here and there to wrap and unwrap JSON data.'''
        return cls.__name__.lower()
    
    def __init__(self, redmine, update_fn, json_data=None, data={}):
        self._redmine = redmine
        self._update_fn = update_fn
        self._type = self._get_type()
        
        if json_data:
            # Parse the data
            try:
                data = json.loads(json_data)
            except ValueError:
                # If parsing failed, then raise the string which likely contains an error message instead of data
                raise RedmineError(json_data)

        # Check to see if there is a data wrapper
        # Some replies will have {'issue':{<data>}} instead of just {<data>}
        try:
            data = data[self._type]
        except KeyError:
            pass

        # Map all dictionary data to object attributes
        self.__dict__.update(data)

        # Map custom fields into our custom fields object
        try:
            self.custom_fields = Custom_Fields(self.custom_fields)
        except AttributeError:
            pass

        # Set the changes dict to track all changes from here on out
        self._changes = {}

    def __repr__(self):
        return '<Redmine %s #%s>' % (self._type, self.id)
    
    def __int__(self):
        return self.id
    
    def __str__(self):
        try:
            return self.name
        except:
            return self.__repr__()
        
    def __setattr__(self, name, value):
        '''Set the attribute for any non-protected attribute.'''
        if name in self._protected_attr:
            raise AttributeError("Can't set attribute %s." % name)
        # Track any new changes for later saving
        try:
            self._changes[name] = value
        except TypeError:
            pass
        
        # Set the instance value
        self.__dict__[name] = value

    def _check_custom_fields(self):
        # Check for any changes in the custom fields, if mapped
        if self._changes.has_key('custom_fields'):
            # it's a new field - copied outside our scope
            try:
                # Try to grab changes from the object
                self._changes['custom_field_values'] = self.custom_fields._get_all()
            except AttributeError:
                pass
            else:
                del(self._changes['custom_fields'])
                return

            try:
                # Try and remap to the required dictionary
                self._changes['custom_field_values'] = { f['id']:f.get('value','') for f in self._changes['custom_fields']}
            except:
                pass
            else:
                del(self._changes['custom_fields'])
            return
        
        try:
            if self.custom_fields.changed:
                custom_changed = self.custom_fields
            else:
                return
        except AttributeError:
            return
        
        # We've got changes, map them to the required field
        self._changes['custom_field_values'] = custom_changed._get_changes()

    @classmethod
    def _remap_tag_to_tag_id(cls, tag, new_data):
        '''Remaps a given changed field from tag to tag_id.'''
        try:
            value = new_data[tag]
        except:
            # If tag wasn't changed, just return
            return
        
        tag_id = tag + '_id'
        try:
            # Remap the ID change to the required field
            new_data[tag_id] = value['id']
        except:
            try:
                # Try and grab the id of the object
                new_data[tag_id] = value.id
            except AttributeError:
                # If the changes field is not a dict or object, just use whatever value was given
                new_data[tag_id] = value
        
        # Remove the tag from the changed data
        del new_data[tag]
        

    def save(self, notes=None):
        '''Save all changes (if any) back to Redmine.'''
        self._check_custom_fields()
                
        if not self._changes:
            return None
                
        for tag in self._remap_to_id:
            self._remap_tag_to_tag_id(tag, self._changes)
                
        try:
            self._update_fn(self.id, **self._changes)
        except:
            raise
        else:
            # Successful save, woot! Now clear the changes dict
            self._changes.clear()

class Custom_Fields(object):
    '''Handler to make custom fields easy to deal with.'''
    changed = False
    
    def __init__(self, custom_field_data):
        self._get_ref = {}
        self._data = custom_field_data
        
        # Map the field data to easy-to-access dicts
        for field in custom_field_data:
            self._get_ref[field['id']] = field
            try:
                self._get_ref[field['name']] = field
            except KeyError:
                pass

    def __repr__(self):
        return '<Custom Fields: %s>' % self._data
    
    def _get_all(self):
        '''Return all values.'''
        return { f['id']:f.get('value','') for f in self._data }

    def _get_changes(self):
        '''Get all changed values.'''
        result = { f['id']:f.get('value','') for f in self._data if f.get('changed', False)}
        self._clear_changes
        return result
        
    def _clear_changes(self):
        '''Reset the changed flags'''
        self.changed = False
        for f in self._data:
            del(f['changed'])
    
    def __getitem__(self, key):
        # returned when self[key] is called
        return self._get_ref[key].get('value', None)

    def __setitem__(self, key, value):
        # returned when self[key]=value
        field = self._get_ref[key]
        field['value'] = value
        field['changed'] = True
        self.changed = True
    

class Redmine_Items_Manager(object):
    _object = Redmine_Item
    
    _query_path = ''
    _query_container = ''
    _item_path = ''
    _item_new_path = ''
    
    def __init__(self, redmine, item_obj=None):
        self._redmine = redmine
        
        if item_obj:
            self._object = item_obj
        
        # Grab data about the object
        self._item_type = self._object._get_type()
        self._item_name = self._object.__name__
        
        self._query_path = self._object._query_path
        self._query_container = self._object._query_container
        self._item_path = self._object._item_path
        self._item_new_path = self._object._item_new_path
    
    def __getitem__(self, key):
        # returned when self[key] is called
        try:
            return self.get(key)
        except urllib2.HTTPError, e:
            # Remap 404 errors to a proper dict error
            if e.code == 404:
                raise KeyError('%s %r not on server.' % (self._item_name, key))
            else:
                # All other errors just flow up
                raise

    def __iter__(self):
        # Called when   for item in items:
        return self.query()
    
    def __call__(self, **options):
        # when called as if it were a function, perform a query and return an iterable
        # for item in items(status_id='closed'):
        return self.query(**options)
    
    def items(self, **options):
        '''Return a query interator with (id, object) pairs.'''
        iter = self.query(**options)
        while True:
            obj = iter.next()
            yield (obj.id, obj)
    
    def query_to_dict(self, **options):
        '''Run a query and return all results as a dictionary'''
        return dict(self.items(**options))
    
    def query_to_list(self, **options):
        '''Run a query and return all results as a list'''
        return list(self.query(**options))
    
    def _objectify(self, json_data=None, data={}):
        '''Return an object derived from the given json data.'''
        return self._object(self._redmine, self.update, json_data=json_data, data=data)
    
    def new(self, **dict):
        '''Create a new item with the provided dict information.  Returns the new item.'''
        if not self._item_new_path:
            raise AttributeError('new is not available for %s' % self._item_name)

        # Remap various tag to tag_id
        for tag in self._object._remap_to_id:
            self._object._remap_tag_to_tag_id(tag, dict)
        
        target = self._item_new_path
        payload = json.dumps({self._item_type:dict})    
        json_data = self._redmine.post(target, payload)
        return self._objectify(json_data)
    
    def get(self, id):
        '''Get a single item with the given ID'''
        if not self._item_path:
            raise AttributeError('get is not available for %s' % self._item_name)
        target = self._item_path % id
        json_data = self._redmine.get(target)
        return self._objectify(json_data)
    
    def update(self, id, **dict):
        '''Update a given item with the passed data.'''
        if not self._item_path:
            raise AttributeError('update is not available for %s' % self._item_name)
        target = self._item_path % id
        payload = json.dumps({self._item_type:dict})    
        self._redmine.put(target, payload)
        return None    
        
    def delete(self, id):
        '''Delete a single item with the given ID'''
        if not self._item_path:
            raise AttributeError('delete is not available for %s' % self._item_name)
        target = self._item_path % id
        self._redmine.delete(target)
        return None
    
    def query(self, **options):
        '''Return an iterator for the given items.'''    
        if not self._query_path:
            raise AttributeError('query is not available for %s' % self._item_name)
        last_item = 0
        offset = 0
        current_item = None
        limit = options.get('limit', 25)
        options['limit'] = limit
        target = self._query_path
        while True:
            options['offset'] = offset
            # go get the data with the given offset
            json_data = self._redmine.get(target, options)
            # Try and read the json
            try:
                data = json.loads(json_data)
            except:
                raise RedmineError(json_data)
            
            # The data is enclosed in the _query_container item
            # That is, {'issues':{(issue1),(issue2)...}, 'total_count':##}
            data_container = data[self._query_container]
            for item_data in data_container:
                yield(self._objectify(data=item_data))
            
            # If the container was empty, we requested past the end, just exit
            if not data_container:
                break
            try:
                if int(data['total_count']) > ( offset + len(data_container) ):
                    # moar data!
                    offset += limit
                else:
                    break
            except:
                # If we don't even have a 'total_count', we're done.
                break

class Redmine_WS(object):
    '''Base class to handle all the Redmine lower-level interactions.'''
    
    def __init__(self, url, key=None, username=None, password=None, debug=False, readonlytest=False, version=0.0 ):
        self._url = url
        self._key = key
        self.debug = debug
        self.readonlytest = readonlytest
        self._set_version(version)
        if readonlytest:
            print 'Redmine instance running in read only test mode.  No data will be written to the server.'
                    
        self._setup_authentication(username, password)
                                

    # extend the request to handle PUT command
    class PUT_Request(urllib2.Request):
        def get_method(self):
            return 'PUT'

    # extend the request to handle DELETE command
    class DELETE_Request(urllib2.Request):
        def get_method(self):
            return 'DELETE'
    
    def _setup_authentication(self, username, password):
        '''Create the authentication object with the given credentials.'''

        ## BUG WORKAROUND
        if self.version < 1.1:
            # Version 1.0 had a bug when using the key parameter.
            # Later versions have the opposite bug (a key in the username doesn't function)
            if not username:
                username = self._key
                self._key = None
        
        if not username:
            return
        if not password:
            password = '12345'  #the same combination on my luggage!  (required dummy value)
            
        #realm = 'Redmine API' - doesn't always work
        # create a password manager
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()

        password_mgr.add_password(None, self._url, username, password )
        handler = urllib2.HTTPBasicAuthHandler( password_mgr )

        # create "opener" (OpenerDirector instance)
        self._opener = urllib2.build_opener( handler )

        # set the opener when we fetch the URL
        self._opener.open( self._url )

        # Install the opener.
        urllib2.install_opener( self._opener )
    
    def open_raw(self, page, parms=None, payload=None, HTTPrequest=None, payload_type='application/json' ):
        '''Opens a page from the server with optional XML.  Returns a response file-like object'''
        if not parms:
            parms={}
        
        # if we're using a key, but it's not going in the header, add it to the parms array
        if self._key and not self.key_in_header:
            parms['key'] = self._key
        
        # encode any data
        urldata = ''
        if parms:
            urldata = '?' + urllib.urlencode( parms )
        
        
        fullUrl = self._url + '/' + page
        
        # register this url to be used with the opener
        # must be registered for each unique path
        try:
            self._opener.open( fullUrl )
        except AttributeError:
            # No authentication
            pass
            
        #debug
        if self.debug:
            print fullUrl + urldata
        
        # Set up the request
        if HTTPrequest:
            request = HTTPrequest( fullUrl + urldata )
        else:
            request = urllib2.Request( fullUrl + urldata )
            
        # If the key is set and in the header, add it
        if self._key and self.key_in_header:
            request.add_header('X-Redmine-API-Key', self._key)
            
        # get the data and return XML object
        if payload:
            request.add_header('Content-Type', payload_type)
            response = urllib2.urlopen( request, payload )            
        else:
            response = urllib2.urlopen( request )
        
        return response
    
    def open(self, page, parms=None, payload=None, HTTPrequest=None ):
        '''Opens a page from the server with optional content.  Returns the string response.'''
        response = self.open_raw( page, parms, payload, HTTPrequest )
        return response.read()
        
    
    def get(self, page, parms=None ):
        '''Gets an XML object from the server - used to read Redmine items.'''
        return self.open( page, parms )
    
    def post(self, page, payload, parms=None ):
        '''Posts a string payload to the server - used to make new Redmine items.  Returns an JSON string or error.'''
        if self.readonlytest:
            print 'Redmine read only test: Pretending to create: ' + page
            return payload
        else:
            return self.open( page, parms, payload )
    
    def put(self, page, payload, parms=None ):
        '''Puts an XML object on the server - used to update Redmine items.  Returns nothing useful.'''
        if self.readonlytest:
            print 'Redmine read only test: Pretending to update: ' + page
        else:
            return self.open( page, parms, payload, HTTPrequest=self.PUT_Request )
    
    def delete(self, page ):
        '''Deletes a given object on the server - used to remove items from Redmine.  Use carefully!'''
        if self.readonlytest:
            print 'Redmine read only test: Pretending to delete: ' + page
        else:
            return self.open( page, HTTPrequest=self.DELETE_Request )

    
    
            