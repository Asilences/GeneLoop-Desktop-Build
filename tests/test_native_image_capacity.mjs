import test from 'node:test';
import assert from 'node:assert/strict';
import {Context} from '@deepseek-ai/cordis';
import {LocalAttachmentStore} from '@deepseek-ai/dsh-attachment-local';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
test('actual DSH store admits 20 MiB original image and rejects one byte over',async()=>{
 const home=mkdtempSync(join(tmpdir(),'geneloop-native-image-capacity-'));
 const store=new LocalAttachmentStore(new Context(),{dshHome:home});
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMUkdNgYGBgYgADAAROAF4By7ZWAAAAAElFTkSuQmCC','base64');
 try{
  const original=Buffer.alloc(20*1024*1024);png.copy(original);
  const ref=await store.saveImage({data:original,mediaType:'image/png',name:'boundary.png'});
  assert.ok(ref);
  const oversized=Buffer.concat([original,Buffer.from([0])]);
  await assert.rejects(store.saveImage({data:oversized,mediaType:'image/png',name:'over.png'}));
 }finally{rmSync(home,{recursive:true,force:true});}
});
