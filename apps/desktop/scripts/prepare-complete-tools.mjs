// Completes a staged tool bundle on the target operating system. Build hosts
// download dependencies; installed applications do not install them on demand.
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {prepareNativeExtras} from './prepare-native-extras.mjs';
import {stagePptProfile} from './stage-ppt-profile.mjs';
const app=fileURLToPath(new URL('../',import.meta.url)),bundle=join(app,'desktop-tools-bundle');
const python=join(bundle,process.platform==='win32'?'python/python.exe':'python/bin/geneloop-python');
prepareNativeExtras(python,bundle);
stagePptProfile(app,bundle);
// GeneLoop PPT authoring excludes voice-over, presentation video and subtitles.
