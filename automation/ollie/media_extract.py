"""Offline document, OCR and speech extraction. Never executes document instructions."""
import argparse
import json
import math
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path


SUPPORTED={'.doc','.docx','.pdf','.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff','.mp4','.mov','.mkv','.webm','.avi'}


class ExtractionError(Exception):
    pass


def run(args,timeout=90,env=None):
    result=subprocess.run(args,capture_output=True,timeout=timeout,env=env)
    if result.returncode:raise ExtractionError('Không đọc được định dạng hoặc tệp bị lỗi.')
    return result.stdout


def ocr(path,root):
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=32_000_000
    with Image.open(path) as original:
        if original.width*original.height>32_000_000:raise ExtractionError('Ảnh vượt giới hạn kích thước.')
        image=ImageOps.exif_transpose(original).convert('RGB')
        if max(image.size)>3200:image.thumbnail((3200,3200))
        if max(image.size)<1600:image=image.resize((image.width*2,image.height*2))
        with tempfile.TemporaryDirectory(dir=root/'work') as tmp:
            normalized=Path(tmp)/'ocr.png';image.save(normalized)
            return run(['tesseract',str(normalized),'stdout','--tessdata-dir',str(root/'models/tessdata'),
                        '-l','vie+eng','--psm','3'],timeout=90).decode('utf-8',errors='replace').strip()


def extract(path,root):
    path=Path(path);root=Path(root);(root/'work').mkdir(parents=True,exist_ok=True)
    suffix=path.suffix.lower();warnings=[];items=[]
    if suffix not in SUPPORTED:raise ExtractionError('Dùng Word .doc/.docx, PDF, ảnh hoặc video MP4/MOV/MKV/WEBM nhé.')
    if not 0<path.stat().st_size<=100*1024*1024:raise ExtractionError('Tệp phải dưới 100 MB và không rỗng.')
    def add(label,text):
        text=str(text).replace('\x00','').strip()
        if text:items.append({'locator':label,'text':text})
    with tempfile.TemporaryDirectory(dir=root/'work') as tmp:
        tmp=Path(tmp)
        if suffix=='.docx':
            from docx import Document
            with zipfile.ZipFile(path) as archive:
                info=archive.infolist()
                if len(info)>3000 or sum(x.file_size for x in info)>80*1024*1024:raise ExtractionError('Word vượt giới hạn dữ liệu giải nén.')
                embedded=[x for x in info if x.filename.startswith('word/media/') and Path(x.filename).suffix.lower() in SUPPORTED]
                if len(embedded)>30:warnings.append('Chỉ nhận chữ trong 30 ảnh nhúng đầu tiên.')
                for n,item in enumerate(embedded[:30],1):
                    image=tmp/('image-'+str(n)+Path(item.filename).suffix.lower());image.write_bytes(archive.read(item))
                    try:add('Ảnh nhúng '+str(n),ocr(image,root))
                    except (ExtractionError,OSError):warnings.append('Một ảnh nhúng chưa nhận được chữ.')
            doc=Document(path)
            for n,block in enumerate(doc.iter_inner_content(),1):
                if hasattr(block,'text'):add('Đoạn '+str(n),block.text)
                elif hasattr(block,'rows'):add('Bảng '+str(n),'\n'.join(' | '.join(c.text for c in row.cells) for row in block.rows))
        elif suffix=='.doc':
            if path.read_bytes()[:8]!=bytes.fromhex('D0CF11E0A1B11AE1'):raise ExtractionError('Tệp .doc không phải Word hợp lệ; hãy lưu thành .docx.')
            binary=root/'bin/antiword-package/usr/bin/antiword'
            env={**os.environ,'ANTIWORDHOME':str(root/'bin/antiword-package/usr/share/antiword')}
            add('Văn bản Word',run([str(binary),'-m','UTF-8.txt',str(path)],env=env).decode('utf-8',errors='replace'))
        elif suffix=='.pdf':
            from pypdf import PdfReader
            reader=PdfReader(path,strict=False)
            if reader.is_encrypted:raise ExtractionError('PDF đang khóa; hãy gửi bản đã mở khóa.')
            if len(reader.pages)>100:raise ExtractionError('PDF vượt 100 trang; hãy chia thành các tệp nhỏ hơn.')
            for n,page in enumerate(reader.pages,1):
                text=page.extract_text() or ''
                if len(text.strip())<30:
                    image=tmp/('page-'+str(n))
                    run(['pdftoppm','-f',str(n),'-l',str(n),'-r','140','-scale-to','3200','-singlefile','-png',str(path),str(image)])
                    text=ocr(image.with_suffix('.png'),root)
                add('Trang '+str(n),text)
        elif suffix in {'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}:
            add('Chữ trong ảnh',ocr(path,root));warnings.append('OCR đọc chữ; không suy đoán hình ảnh không có chữ. Hãy đối chiếu các con số quan trọng.')
        else:
            probe=json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)]))
            duration=float(probe.get('format',{}).get('duration',0))
            if not math.isfinite(duration) or not 0<duration<=1200:raise ExtractionError('Video cần có thời lượng và không dài quá 20 phút.')
            if any(s.get('codec_type')=='audio' for s in probe.get('streams',[])):
                audio=tmp/'audio.wav'
                run(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),'-vn','-ac','1','-ar','16000',str(audio)],timeout=180)
                import onnxruntime
                onnxruntime.disable_telemetry_events()
                from faster_whisper import WhisperModel
                model=WhisperModel(str(root/'models/whisper'),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
                segments,_=model.transcribe(str(audio),beam_size=3,vad_filter=True,condition_on_previous_text=False)
                for segment in segments:
                    if segment.no_speech_prob<.7 and segment.avg_logprob>-1.5:
                        seconds=int(segment.start);add(f'Lời nói {seconds//60:02}:{seconds%60:02}',segment.text)
                del model
            if any(s.get('codec_type')=='video' for s in probe.get('streams',[])):
                interval=max(5,duration/60);last=''
                run(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),'-vf',f'fps=1/{interval},scale=1280:-2','-frames:v','60',str(tmp/'frame-%03d.png')],timeout=180)
                for n,image in enumerate(sorted(tmp.glob('frame-*.png'))):
                    text=ocr(image,root)
                    if text and text!=last:
                        seconds=int(n*interval);add(f'Chữ trên hình khoảng {seconds//60:02}:{seconds%60:02}',text);last=text
                warnings.append('Video nhận lời nói và chữ trên tối đa 60 khung hình mẫu; có thể bỏ sót cảnh nhanh hoặc hình không có chữ.')
            warnings.append('Bản chép lời/OCR tự động có thể sai; cần đối chiếu nguồn với thông số quan trọng.')
    if not items:raise ExtractionError('Chưa nhận được nội dung chữ hoặc lời nói đủ rõ. Hãy gửi bản rõ hơn hoặc kèm chú thích.')
    if sum(len(x['text']) for x in items)>1_500_000:raise ExtractionError('Nội dung quá lớn; hãy chia tài liệu thành các phần nhỏ hơn.')
    return {'items':items,'warnings':list(dict.fromkeys(warnings))}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--path',required=True);parser.add_argument('--root',required=True)
    args=parser.parse_args()
    try:print(json.dumps({'ok':True,**extract(args.path,args.root)},ensure_ascii=False))
    except ExtractionError as error:print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False))
    except Exception:print(json.dumps({'ok':False,'error':'Không đọc được tệp này. Hãy kiểm tra định dạng và thử bản khác.'},ensure_ascii=False))
