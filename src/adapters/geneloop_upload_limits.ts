/** Product file capacity; image admission remains the native DSH contract. */
import {readFileSync} from 'node:fs';
import {DEFAULT_MAX_IMAGE_BYTES,DEFAULT_MAX_IMAGES_PER_MESSAGE,DEFAULT_MAX_MESSAGE_IMAGE_BYTES} from '@deepseek-ai/dsh-attachment-local';
const limits=JSON.parse(readFileSync(new URL('./geneloop_upload_limits.json',import.meta.url),'utf8'));
if(limits.schema_version!==1||!Number.isSafeInteger(limits.file_max_bytes)||limits.file_max_bytes<1)throw Error('invalid upload limits');
export const FILE_MAX_BYTES:number=limits.file_max_bytes;
export const nativeImageLimits={maxImageBytes:DEFAULT_MAX_IMAGE_BYTES,maxImagesPerMessage:DEFAULT_MAX_IMAGES_PER_MESSAGE,maxMessageImageBytes:DEFAULT_MAX_MESSAGE_IMAGE_BYTES};
