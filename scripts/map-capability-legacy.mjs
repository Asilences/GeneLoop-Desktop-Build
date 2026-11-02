#!/usr/bin/env node
/** Fixed offline JSON bridge. Never executes or imports candidate source. */
import {mapLegacyLibrary} from '../src/adapters/capability_contract.ts';
try {
 const chunks=[];let size=0;
 for await(const chunk of process.stdin){size+=chunk.length;if(size>6_000_000)throw Error('capability_legacy_bridge_too_large');chunks.push(chunk);}
 const request=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 if(!request||typeof request.raw_base64!=='string')throw Error('capability_legacy_bridge_invalid');
 const capabilities=mapLegacyLibrary(Buffer.from(request.raw_base64,'base64'),request.owner,request.backend,request.expected_sha256);
 process.stdout.write(JSON.stringify({capabilities}));
}catch(error){
 process.stdout.write(JSON.stringify({error:error instanceof Error?error.message:'capability_legacy_bridge_failed'}));
 process.exitCode=1;
}
