import os
import jinja2
import webapp2
import logging
import json

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from StringIO import StringIO
from PIL import Image
from contextlib import closing
from zipfile import ZipFile, ZIP_DEFLATED

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

class Screenshot(webapp2.RequestHandler):
  def get(self):
    upload_url = blobstore.create_upload_url('/upload')
    template_values = {
      'upload_url': upload_url,
    }

    template = JINJA_ENVIRONMENT.get_template('index.html')
    self.response.write(template.render(template_values))

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
  def post(self):
    upload_files = self.get_uploads('files')
    urls = []    
    for file in upload_files:
      urls.append(str(file.key()))
    upload_url = blobstore.create_upload_url('/upload')
    self.response.out.write(json.dumps({'urls':urls, 'upload_url': upload_url}))

class ZipPackager(webapp2.RequestHandler):
  def get(self):
    images = self.request.get('images')
    zipstream = StringIO()
    with closing(ZipFile(file=zipstream,compression=ZIP_DEFLATED,mode="w")) as outFile:
      for img in images.split(','):
        logging.info(img)
        blob_reader = blobstore.BlobReader(img)
        original = Image.open(StringIO(blob_reader.read()))
        cropped = crop(original)
        output = StringIO()
        cropped.save(output, format="png")
        fname, fext = os.path.splitext(blob_reader.blob_info.filename)
        outFile.writestr(fname+".png", output.getvalue())
    self.response.headers['Content-Type'] ='application/zip'
    self.response.headers['Content-Disposition'] = 'attachment; filename="cropped.zip"'
    self.response.out.write(zipstream.getvalue())
    
class ViewPhotoHandler(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, photo_key):
    if not blobstore.get(photo_key):
      self.error(404)
    else:
      blob_reader = blobstore.BlobReader(photo_key)
      original = Image.open(StringIO(blob_reader.read()))
      s = original.size
      ratio = float(300)/s[0]
      resized = original.resize((int(s[0]*ratio), int(s[1]*ratio)))
      cropped = crop(resized)
      output = StringIO()
      cropped.save(output, format="png")
      self.response.headers['Content-Type'] = 'image/png'
      self.response.out.write(output.getvalue())

def crop(original):
  w,h = original.size
  pixelMap = original.convert('RGB').load()
  #find top bar
  topbar_top_left = pixelMap[0,0]
  topbar_top_right = 0
  topbar_bottom_left = 0
  for i in range(original.size[0]):    
    if topbar_top_left == pixelMap[i,0]:
      topbar_top_right = i
    else:
      break
  for i in range(original.size[1]):
    if topbar_top_left == pixelMap[0,i]:
      topbar_bottom_left = i
    else:
      break
    
  #find bottom bar
  bottombar_bottom_right = pixelMap[w-1,h-1]
  bottombar_top_right = 0
  bottombar_bottom_left = 0
  for i in reversed(range(original.size[0])):    
    if bottombar_bottom_right == pixelMap[i,h-1]:
      bottombar_bottom_left = i
    else:
      break
  for i in reversed(range(original.size[1])):
    if bottombar_bottom_right == pixelMap[w-1,i]:
      bottombar_top_right = i
    else:
      break
  if topbar_top_right > topbar_bottom_left :
    #portrait
    cropped = original.crop((0,topbar_bottom_left,w,bottombar_top_right))
  else:
    #landscape
    cropped = original.crop((topbar_top_right,0,bottombar_bottom_left,h))  
 
  return cropped
  

app = webapp2.WSGIApplication([('/', Screenshot),('/upload', UploadHandler), ('/view/([^/]+)?', ViewPhotoHandler), ('/zip', ZipPackager)], debug=False)
