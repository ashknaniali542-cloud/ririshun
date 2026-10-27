// Reference process boundary only; not an HTTP server or job queue.
// Python executable must be configured by the server administrator, never a request field.
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
const pkg = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export function runPythonFile(scriptPath, args, {timeoutMs=60000, maxBytes=2*1024*1024}={}) {
  return new Promise((resolveJob, reject) => {
    const child=spawn(process.env.RRS_PYTHON || 'python',['-B',scriptPath,...args],{
      cwd:pkg, shell:false, windowsHide:true,
      env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}, stdio:['ignore','pipe','pipe']
    });
    let stdout='',stderr='',bytes=0,finished=false;
    const fail=e=>{if(!finished){finished=true;clearTimeout(timer);child.kill();reject(e);}};
    const timer=setTimeout(()=>fail(new Error('PYTHON_TIMEOUT')),timeoutMs);
    for(const [stream,isOut] of [[child.stdout,true],[child.stderr,false]]){
      stream.setEncoding('utf8');
      stream.on('data',s=>{bytes+=Buffer.byteLength(s);if(bytes>maxBytes){fail(new Error('OUTPUT_LIMIT'));return;}if(isOut)stdout+=s;else stderr+=s;});
    }
    child.on('error',fail);
    child.on('close',code=>{if(finished)return;finished=true;clearTimeout(timer);resolveJob({code,stdout,stderr});});
  });
}
if(process.argv[2]==='--demo'){
  const result=await runPythonFile(resolve(pkg,'04_离线演示/run_demo.py'),[]);
  process.stdout.write(result.stdout);process.stderr.write(result.stderr);
  process.exitCode=result.code ?? 1;
}
// Production worker: use fixed, allow-listed script paths. Resolve data/evidence IDs
// to immutable job directories on the server. Do not forward client paths or commands.
// Parse the report even when process code is 0: NOT_CHECKED and hash mismatch are not PASS.
