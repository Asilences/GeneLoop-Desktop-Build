#!/usr/bin/env node
/** Fixed offline schema bridge to the installed online dialect. No candidate code. */
import {assertSupportedJsonSchema} from '@deepseek-ai/dsh-tools';
try {
 const chunks=[];let size=0;
 for await(const chunk of process.stdin){size+=chunk.length;if(size>4_000_000)throw Error('capability_schema_too_large');chunks.push(chunk);}
 const schemas=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 if(!Array.isArray(schemas)||schemas.length!==2)throw Error('capability_schema_request_invalid');
 for(const schema of schemas)assertSupportedJsonSchema(schema);
 process.stdout.write(JSON.stringify({valid:true}));
}catch{
 process.stdout.write(JSON.stringify({valid:false}));process.exitCode=1;
}
