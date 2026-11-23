/** Content-only native tools. No service, scripts, output paths or pixel geometry. */
export const pptDeckLayouts=['cover','section','bullets','statement','closing','quote','table','image','image-left','image-right','chart'];
export const pptDeckLanguages=['zh','en','bilingual'];
const page={type:'object',properties:{layout:{type:'string',enum:pptDeckLayouts},title:{type:'string'},subtitle:{type:'string'},
 kicker:{type:'string'},text:{type:'string'},bullets:{type:'array',items:{type:'string'}},
 rows:{type:'array',items:{type:'array',items:{type:'string'}}},notes:{type:'string'},
 image:{type:'object',properties:{src:{type:'string'},alt:{type:'string'},caption:{type:'string'},fit:{type:'string',enum:['contain','cover']}},required:['src'],additionalProperties:false},
 chart:{type:'object',properties:{kind:{type:'string',enum:['column','bar','line','pie']},categories:{type:'array',items:{type:'string'}},
  series:{type:'array',items:{type:'object',properties:{name:{type:'string'},values:{type:'array',items:{type:'number'}}},required:['name','values'],additionalProperties:false}},
  unit:{type:'string'},caption:{type:'string'}},required:['categories','series'],additionalProperties:false},
 sources:{type:'array',items:{type:'string'}}},additionalProperties:false};
export const pptDeckBuildTool={name:'build_ppt',
 description:'一次提交整份PPT内容并生成可编辑PPTX及PDF/PNG预览。name是新项目简名；plan含title、slides、可选theme/language/target_slide_count/strict_slide_count/sources。每页layout选cover/section/bullets/statement/closing/quote/table/image/image-left/image-right/chart，填写内容而非坐标。bullets最多8条；table.rows含表头，每页8行自动续页，最多8列、单元格60字；chart为kind(column/bar/line/pie)、categories和series[{name,values}]。image.src只接受已有本会话图片；sources写来源引用，保存在备注。保留原始数值；不自动搜图。严格页数会在分页后核对。提交真实整稿，不用单页探测接口；选定后用patch_ppt改同稿，缺页可append_slides补齐，不另建重做。复杂特殊绘图继续原SVG路线。',
 parameters:{type:'object',properties:{name:{type:'string'},plan:{type:'object',properties:{title:{type:'string'},
  slides:{type:'array',items:{...page,required:['layout','title']}},theme:{type:'string'},language:{type:'string',enum:pptDeckLanguages},
  target_slide_count:{type:'integer'},strict_slide_count:{type:'boolean'},sources:{type:'array',items:{type:'string'}}},required:['title','slides'],additionalProperties:false}},required:['name','plan'],additionalProperties:false}};
export const pptDeckPatchTool={name:'patch_ppt',
 description:'按稳定slide_id批量修改build_ppt创建的同一JSON稿件，并自动返回当前PPTX/PDF/PNG。project及expected_revision必须来自当前回执，0是有效版本。edits:[{slide_id,changes:{title/text/bullets/rows/image/chart/notes等}}]；只提交变化字段，保留其他页。append_slides可在同稿追加1–5个内容页，配合edits=[]补齐不完整草稿；不要编造slide_id。edits为空时读取当前版本并复用或恢复导出，无需重做稿件。版本冲突返回当前revision。外部Office手工修改不覆盖，改用edit_ppt_native编辑原件。',
 parameters:{type:'object',properties:{project:{type:'string'},expected_revision:{type:'integer'},edits:{type:'array',items:{type:'object',properties:{slide_id:{type:'string'},changes:page},required:['slide_id','changes'],additionalProperties:false}},append_slides:{type:'array',items:{...page,required:['layout','title']}}},required:['project','expected_revision','edits'],additionalProperties:false}};
