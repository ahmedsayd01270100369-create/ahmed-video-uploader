import os,secrets
from urllib.parse import urlencode
from flask import Flask,render_template,redirect,request,jsonify,session
import requests
app=Flask(__name__);app.secret_key=os.environ['FLASK_SECRET_KEY']
KEY=os.environ['TIKTOK_CLIENT_KEY'];SECRET=os.environ['TIKTOK_CLIENT_SECRET'];REDIRECT=os.environ['TIKTOK_REDIRECT_URI']
AUTH='https://www.tiktok.com/v2/auth/authorize/';TOKEN='https://open.tiktokapis.com/v2/oauth/token/';API='https://open.tiktokapis.com/v2'
@app.get('/')
def home(): return render_template('index.html')
@app.get('/callback/')
def callback():
 c=request.args.get('code');s=request.args.get('state')
 if not c or s!=session.pop('state',None): return 'Invalid OAuth response',400
 r=requests.post(TOKEN,data={'client_key':KEY,'client_secret':SECRET,'code':c,'grant_type':'authorization_code','redirect_uri':REDIRECT},timeout=30)
 if not r.ok:return r.text,400
 d=r.json();session['access_token']=d['access_token'];session['refresh_token']=d.get('refresh_token');return redirect('/?connected=1')
@app.get('/oauth')
def oauth():
 s=secrets.token_urlsafe(32);session['state']=s
 return redirect(AUTH+'?'+urlencode({'client_key':KEY,'response_type':'code','scope':'user.info.basic,video.publish,video.upload','redirect_uri':REDIRECT,'state':s}))
def h(): return {'Authorization':'Bearer '+session['access_token']}
@app.get('/api/session')
def sess():
 if 'access_token' not in session:return jsonify(connected=False)
 r=requests.get(API+'/user/info/?fields=open_id,display_name',headers=h(),timeout=20)
 if not r.ok:return jsonify(connected=False)
 u=r.json().get('data',{}).get('user',{});return jsonify(connected=True,display_name=u.get('display_name'))
@app.post('/api/creator-info')
def creator():
 r=requests.post(API+'/post/publish/creator_info/query/',headers={**h(),'Content-Type':'application/json'},timeout=30);return (r.text,r.status_code,{'Content-Type':'application/json'})
@app.post('/api/publish')
def publish():
 v=request.files.get('video')
 if not v:return jsonify(error='No video selected'),400
 data=v.read();size=len(data);chunk=size if size<5*1024*1024 else 5*1024*1024;total=(size+chunk-1)//chunk
 payload={'post_info':{'title':request.form.get('caption','')[:2200],'privacy_level':request.form.get('privacy_level','SELF_ONLY'),'disable_comment':False},'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':chunk,'total_chunk_count':total}}
 r=requests.post(API+'/post/publish/video/init/',headers={**h(),'Content-Type':'application/json'},json=payload,timeout=30)
 if not r.ok:return jsonify(error=r.text),r.status_code
 d=r.json().get('data',{});url=d.get('upload_url')
 if not url:return jsonify(error='No upload URL returned'),502
 for i in range(total):
  a=i*chunk;b=min(size,a+chunk)-1;part=data[a:b+1]
  u=requests.put(url,headers={'Content-Type':'video/mp4','Content-Length':str(len(part)),'Content-Range':f'bytes {a}-{b}/{size}'},data=part,timeout=120)
  if u.status_code not in (200,201,206):return jsonify(error=u.text),502
 return jsonify(message='Video uploaded to TikTok.',publish_id=d.get('publish_id'))
@app.post('/api/draft')
def draft(): return jsonify(error='Draft flow needs its separate video.upload implementation.'),501
@app.get('/terms.html')
def terms(): return '<h1>Terms of Service</h1><p>Users are responsible for content they submit.</p>'
@app.get('/privacy.html')
def privacy(): return '<h1>Privacy Policy</h1><p>OAuth tokens are handled server-side.</p>'
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
