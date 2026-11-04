import test from 'node:test';
import assert from 'node:assert/strict';
import {assertComponentSchema,validateComponentParameters,bindComponentConstants,normalizeComponentSchema} from '../src/adapters/ppt_component_schema.ts';

test('only explicit structural constants are filled without historical content defaults',()=>{
 const schema={type:'object',properties:{wrap:{type:'number',const:64},title:{type:'string'}},required:['title']};
 assert.deepEqual(bindComponentConstants(schema,{title:'Current paper'}),{title:'Current paper',wrap:64});
 assert.deepEqual(bindComponentConstants(schema,{title:'Current paper',wrap:12}),{title:'Current paper',wrap:12});
});

test('component schema preserves item, Unicode text and numeric capacity constraints',()=>{
 const schema={type:'object',properties:{lines:{type:'array',minItems:1,maxItems:2,items:{type:'string',maxLength:3}},size:{type:'number',minimum:12,maximum:40}},required:['lines','size'],additionalProperties:false};
 assertComponentSchema(schema);
 assert.deepEqual(validateComponentParameters(schema,{lines:['中😀文'],size:24}),[]);
 assert.ok(validateComponentParameters(schema,{lines:[],size:24}).length);
 assert.ok(validateComponentParameters(schema,{lines:['超过三字'],size:41}).length);
 assert.throws(()=>assertComponentSchema({type:'string',pattern:'.*'}));
 assert.throws(()=>assertComponentSchema({type:'array',minItems:-1}));
});

test('oneOf remains exclusive when branches differ only in bounded array lengths',()=>{
 const schema={oneOf:[{type:'array',minItems:1,maxItems:1,items:{type:'string'}},{type:'array',minItems:2,maxItems:2,items:{type:'string'}}]};
 assertComponentSchema(schema);
 assert.deepEqual(validateComponentParameters(schema,['one']),[]);
 assert.deepEqual(validateComponentParameters(schema,['one','two']),[]);
 assert.ok(validateComponentParameters(schema,[]).length);
 assert.ok(validateComponentParameters(schema,['a','b','c']).length);
});

test('local definitions retain nested text and list capacity online',()=>{
 const schema={type:'object',$defs:{run:{type:'object',properties:{text:{type:'string',maxLength:4},bold:{type:'boolean'}},required:['text'],additionalProperties:false}},
  properties:{title:{type:'array',maxItems:2,items:{$ref:'#/$defs/run'}},wrap:{$ref:'#/$defs/width'}},required:['title']};
 schema.$defs.width={type:'number',const:64};
 assertComponentSchema(schema);
 assert.equal(normalizeComponentSchema(schema).$defs,undefined);
 assert.deepEqual(bindComponentConstants(schema,{title:[{text:'当前论文'}]}),{title:[{text:'当前论文'}],wrap:64});
 assert.deepEqual(validateComponentParameters(schema,{title:[{text:'当前论文',bold:true}]}),[]);
 assert.ok(validateComponentParameters(schema,{title:[{text:'超出容量的正文'}]}).length);
 assert.ok(validateComponentParameters(schema,{title:[{text:'a'},{text:'b'},{text:'c'}]}).length);
 assert.ok(validateComponentParameters(schema,{title:[{text:'a',unknown:true}]}).length);
});

test('component definitions reject external, recursive, missing and semantic sibling references',()=>{
 assert.throws(()=>assertComponentSchema({$ref:'https://example.org/schema'}),/local_reference/);
 assert.throws(()=>assertComponentSchema({$ref:'#/$defs/missing'}),/missing_or_recursive/);
 assert.throws(()=>assertComponentSchema({$defs:{loop:{$ref:'#/$defs/loop'}},type:'object',properties:{a:{$ref:'#/$defs/loop'}}}),/missing_or_recursive/);
 assert.throws(()=>assertComponentSchema({$defs:{text:{type:'string'}},type:'object',properties:{a:{$ref:'#/$defs/text',maxLength:2}}}),/siblings_unsupported/);
});
