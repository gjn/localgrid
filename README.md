localgrid
=========

Create UTF grid from postGis database using OGR library

Heavily inspired by ogr_renderer.py at https://github.com/springmeyer/utfgrid-example-writers

Usage
=====

Create dbconnection.py file at same level as localgrid.py containing the database
connection string (including passwords and database to choose).

For example

    dbconnection = 'host=host_url user=dbuser password=dbpassword dbname=database'

Adapt `query()` to query your database (query must include a geometry column)
Adapt `getutfbox` to specify extend of your utfgrid

Sample
=======
Sample file: https://github.com/gjn/localgrid/blob/master/utfgrid.json which corresponds
more or less to http://s.geo.admin.ch/d037d8769
