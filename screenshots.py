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
    type = self.request.get('type')
    images = self.request.get('images')
    zipstream = StringIO()
    with closing(ZipFile(file=zipstream,compression=ZIP_DEFLATED,mode="w")) as outFile:
      for img in images.split(','):
        logging.info(img)
        blob_reader = blobstore.BlobReader(img)
        original = Image.open(StringIO(blob_reader.read()))
        cropped = process(original,type)
        output = StringIO()
        cropped.save(output, format="png")
        fname, fext = os.path.splitext(blob_reader.blob_info.filename)
        outFile.writestr(fname+".png", output.getvalue())
    self.response.headers['Content-Type'] ='application/zip'
    self.response.headers['Content-Disposition'] = str('attachment; filename="sanitized_'+ type+'.zip"')
    self.response.out.write(zipstream.getvalue())
    
class ViewPhotoHandler(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, photo_key):
    if not blobstore.get(photo_key):
      self.error(404)
    else:
      logging.info('display')
      type = self.request.get('type')
      blob_reader = blobstore.BlobReader(photo_key)
      original = Image.open(StringIO(blob_reader.read()))
      s = original.size
      ratio = float(300)/s[0]
      resized = original.resize((int(s[0]*ratio), int(s[1]*ratio)))
      #resized = original
      cropped = process(resized, type)
      output = StringIO()
      cropped.save(output, format="png")
      self.response.headers['Content-Type'] = 'image/png'
      self.response.cache_control = 'public'
      self.response.cache_control.max_age = 86400
      self.response.out.write(output.getvalue())

def process(original, type):
  w,h = original.size
  tb_template = None
  pixelMap = original.load()
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
    if type == 'holo':
      tb_template = prepare_template('templates/topcorner.png', w, topbar_bottom_left)
    elif type == 'kitkat':
      tb_template = prepare_template('templates/topcorner_grey.png', w, topbar_bottom_left)
	
    if tb_template:
      tb_template_data = tb_template.load()
      for i in range(0,w):
        for j in range(0, topbar_bottom_left):
          pixelMap[i,j] = tb_template_data[i,j]      
          cropped = original  
    else:
      cropped = original.crop((0,topbar_bottom_left,w,bottombar_top_right))
  else:
    #landscape
    logging.info(type)
    if type == 'holo':
      tb_template = prepare_template_land('templates/topcorner_land.png', topbar_top_right, h)
    elif type == 'kitkat':
      tb_template = prepare_template_land('templates/topcorner_land_grey.png', topbar_top_right, h)

    if tb_template:
      tb_template_data = tb_template.load()
      for i in range(0,topbar_top_right):
        for j in range(0, h):
          pixelMap[i,j] = tb_template_data[i,j]      
          cropped = original        
    else:
      cropped = original.crop((topbar_top_right,0,bottombar_bottom_left,h))  
 
  return cropped

def prepare_template(file, width, height):
  template = Image.open(file)
  w,h = template.size
  ratio = float(height)/h
  template = template.resize((int(w*ratio), height))
  w,h = template.size
  templateData = template.load()
  result = Image.new('RGB', (width,height),0)
  resultData = result.load()
  for i in range((width-w),width):
    for j in range(0,height):
      resultData[i,j] = templateData[w-width+i,j]
  return result

def prepare_template_land(file, width, height):
  template = Image.open(file)
  w,h = template.size
  ratio = float(width)/w
  template = template.resize((width,int(h*ratio)))
  w,h = template.size
  templateData = template.load()
  result = Image.new('RGB', (width,height),0)
  resultData = result.load()
  for i in range(0,width):
    for j in range(0, h):
      resultData[i,j] = templateData[i,j]
  return result

app = webapp2.WSGIApplication([('/', Screenshot),('/upload', UploadHandler), ('/view/([^/]+)?', ViewPhotoHandler), ('/zip', ZipPackager)], debug=False)
