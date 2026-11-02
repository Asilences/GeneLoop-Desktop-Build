/** The installed DSH parser remains the authority; this tool never repairs or writes the source. */
import {Context} from '@deepseek-ai/cordis';
import Persistence from '@deepseek-ai/dsh-session-persistence-jsonl';
const ctx=new Context();
try{
 const p=new Persistence(ctx,{root:process.argv[2]});
 const handle=await p.open(process.argv[3],'read');
 try{const value=await handle.read();console.log(JSON.stringify({session_id:handle.header.id,events:value.events.length,native_read_passed:true}));}
 finally{await handle.close();}
}finally{await ctx.fiber.dispose();}
