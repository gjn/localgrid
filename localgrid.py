#!/usr/bin/env python
# -*- coding: utf-8 -*-

import osgeo.ogr as ogr
import re
import time
import io

from dbconnection import dbconnection

try:
    import json
except ImportError:
    import simplejson as json

class Extent:
    def __init__(self,minx,miny,maxx,maxy):
        self.minx = float(minx)
        self.miny = float(miny)
        self.maxx = float(maxx)
        self.maxy = float(maxy)

    def width(self):
        return self.maxx - self.minx

    def height(self):
        return self.maxy - self.miny

    def __repr__(self):
        return 'Extent(%s,%s,%s,%s)' % (self.minx,self.miny,self.maxx,self.maxy)


class Request:
    def __init__(self,width,height,extent):
        assert isinstance(extent,Extent)
        assert isinstance(width,int)
        assert isinstance(height,int)
        self.width = width
        self.height = height
        self.extent = extent

class CoordTransform:
    def __init__(self,request,offset_x=0.0,offset_y=0.0):
        assert isinstance(request,Request)
        assert isinstance(offset_x,float)
        assert isinstance(offset_y,float)
        self.request = request
        self.extent = request.extent
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.sx = (float(request.width) / self.extent.width())
        self.sy = (float(request.height) / self.extent.height())

    def forward(self,x,y):
        """Lon/Lat to pixmap"""
        x0 = (x - self.extent.minx) * self.sx - self.offset_x
        y0 = (self.extent.maxy - y) * self.sy - self.offset_y
        return x0,y0

    def backward(self,x,y):
        """Pixmap to Lon/Lat"""
        x0 = self.extent.minx + (x + self.offset_x) / self.sx
        y0 = self.extent.maxy - (y + self.offset_y) / self.sy
        return x0,y0

def escape_codepoints(codepoint):
    """Skip the codepoints that cannot be encoded directly in JSON.
    """
    if codepoint == 34:
        codepoint += 1 # skip "
    elif codepoint == 92:
        codepoint += 1 # Skip backslash
    return codepoint

def decode_id(codepoint):
    codepoint = ord(codepoint)
    if codepoint >= 93:
        codepoint-=1
    if codepoint >= 35:
        codepoint-=1
    codepoint -= 32
    return codepoint

class Grid:
    def __init__(self,resolution=4):
        self.rows = []
        self.feature_cache = {}
        self.resolution = resolution

    def width(self):
        return len(self.rows)

    def height(self):
        return len(self.rows)

    def encode(self):
        keys = {}
        key_order = []
        data = {}
        utf_rows = []
        codepoint = 32
        for y in xrange(0,self.height()):
            row_utf = u''
            row = self.rows[y]
            for x in xrange(0,self.width()):
                feature_id = row[x]
                if feature_id in keys:
                    row_utf += unichr(keys[feature_id])
                else:
                    codepoint = escape_codepoints(codepoint)
                    keys[feature_id] = codepoint
                    key_order.append(feature_id)
                    if self.feature_cache.get(feature_id):
                        data[feature_id] = self.feature_cache[feature_id]
                    row_utf += unichr(codepoint)
                    codepoint += 1
            utf_rows.append(row_utf)

        utf = {}
        utf['grid'] = utf_rows
        utf['keys'] = [unicode(key) for key in key_order]
        utf['data'] = data
        return utf

class Renderer:
    def __init__(self,grid,ctrans,fid_column):
        self.grid = grid
        self.ctrans = ctrans
        self.req = ctrans.request
        self.fid_column = fid_column

    def apply(self,layer,field_names=[]):
        layer_def = layer.GetLayerDefn()
        fields = {}
        for i in range(layer_def.GetFieldCount()):
            field = layer_def.GetFieldDefn(i)
            if field.GetName() in field_names: 
                fields[i] = {'name': field.GetName(), 'type': field.GetTypeName() }
        if len(fields.keys()) == 0:
            raise Exception("No valid fields, field_names was %s")


        layer.ResetReading()

        #we cache our features to not tap the database for every pixel
        features = []
        temp_feat = layer.GetNextFeature()
        while temp_feat is not None:
            features.append(temp_feat)
            temp_feat = layer.GetNextFeature()

        for y in xrange(0,self.req.height,self.grid.resolution):
            row = []
            for x in xrange(0,self.req.width,self.grid.resolution):
                minx,maxy = self.ctrans.backward(x,y)
                maxx,miny = self.ctrans.backward(x+self.grid.resolution, y+self.grid.resolution)
                wkt = 'POLYGON ((%f %f, %f %f, %f %f, %f %f, %f %f))' \
                   % (minx, miny, minx, maxy, maxx, maxy, maxx, miny, minx, miny)
                g = ogr.CreateGeometryFromWkt(wkt)
                found = False

                for feat in features:
                    geom = feat.GetGeometryRef()
                    # we always take the first feature intersecting with the given utfgrid pixel
                    if geom.Intersects(g):
                        #feat.GetFID() is not unique between different ResetReadings (because no FID column is specified
                        #feature_id = feat.GetFID()
                        attr = {}
                        for index, field in fields.iteritems():
                            field_type = field['type'] #.GetTypeName()
                            field_name = field['name'] #.GetName()
                            if field_type == "Integer":
                                attr[field_name] = feat.GetFieldAsInteger(index)
                            elif field_type == "Real":
                                attr[field_name] = feat.GetFieldAsDouble(index)
                            else:
                                attr[field_name] = feat.GetFieldAsString(index)
                            
                        feature_id = int(attr[self.fid_column])
                        row.append(feature_id)
                        self.grid.feature_cache[feature_id] = attr
                        found = True
                        break
                
                if not found:
                    row.append("")

            self.grid.rows.append(row)

def resolve(grid,row,col):
    """ Resolve the attributes for a given pixel in a grid.
    """
    row = grid['grid'][row]
    utf_val = row[col]
    codepoint = decode_id(utf_val)
    key = grid['keys'][codepoint]
    return grid['data'].get(key)

def query():
    return "the_geom,gemname,flaeche,id FROM tlm.swissboundaries_gemeinden"

def getutfbox():
   return Extent(622000,125000,632000,135000)
  #  return Extent(628400,128800,628500,128900)

def getbbox():
    ub = getutfbox()
    wkt = "POLYGON((%d %d,%d %d,%d %d,%d %d,%d %d))"%(ub.minx, ub.miny,
                                                      ub.minx, ub.maxy,
                                                      ub.maxx, ub.maxy,
                                                      ub.maxx, ub.miny,
                                                      ub.minx, ub.miny)
    return ogr.CreateGeometryFromWkt(wkt)
    
if __name__ == "__main__":
    start = time.time();

    ds = ogr.Open("PG:%s "%dbconnection.strip('"'))
    
    if ds is None:
        raise Exception("PostGIS connection failed: '%s'"%dbconnection)

    q = query()
    for sql in re.split('"\W*"', q):
        layer = ds.ExecuteSQL("SELECT " + sql.strip('" '), getbbox())
        if layer is not None:
            tile = Request(256, 256, getutfbox())
            ctrans = CoordTransform(tile)
            grid = Grid(resolution=1)
            rend = Renderer(grid,ctrans,'id')
            rend.apply(layer,field_names=['gemname' ,'flaeche','id'])
            utfgrid = grid.encode()
            #print utfgrid
            with io.open('utfgrid.json', 'w', encoding='utf-8') as f:
                ustring = unicode(json.dumps(utfgrid, indent=4), 'utf-8')
                f.write(ustring)
                f.close()
            
            ds.ReleaseResultSet(layer)

    ds.Destroy()
    print time.time() - start
    
