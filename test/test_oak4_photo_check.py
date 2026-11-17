"""A check never promotes stale, changed-focus or incomplete native captures."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('oak4_photo_check',TOOLS/'oak4_photo_check.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def camera(tmp_path, monkeypatch, overrides=None):
    calls=[]
    def capture(mode,focus):
        index=len(calls);calls.append(index)
        directory=tmp_path/str(index);directory.mkdir()
        frame=dict(width=8000,height=6000,lens_position=116,timestamp_device_s=100.+index)
        if overrides:frame.update(overrides(index))
        metadata=directory/'metadata.json'
        metadata.write_text(json.dumps(dict(success=True,device_id='camera-A',standard=frame,depthai='3.12.0')))
        return dict(directory=str(directory),metadata=str(metadata),images={'standard':str(directory/'image.png')})
    monkeypatch.setattr(module,'image_info',lambda path:dict(width=8000,height=6000,sha256=str(path)))
    return SimpleNamespace(capture=capture),calls


def test_complete_repeated_native_check_preserves_all_provenance(tmp_path,monkeypatch):
    c,calls=camera(tmp_path,monkeypatch)
    report=module.check_standard(c,count=3,report_path=tmp_path/'report.json')
    assert report['passed'] and len(calls)==3
    assert all(r['device_id']=='camera-A' and r['sdk']=='3.12.0' for r in report['captures'])
    assert json.loads((tmp_path/'report.json').read_text())==report


@pytest.mark.parametrize('bad',[
    dict(lens_position=117),dict(width=4000),dict(timestamp_device_s=100.),dict(timestamp_device_s=float('nan'))])
def test_first_bad_frame_stops_check_without_another_camera_start(tmp_path,monkeypatch,bad):
    c,calls=camera(tmp_path,monkeypatch,lambda i:bad if i==1 else {})
    report=module.check_standard(c,count=3,report_path=tmp_path/'report.json')
    assert not report['passed'] and len(calls)==2 and report['captures'][0]['success']
    assert report['captures'][1]['error']


def test_payload_repetition_and_decode_failure_are_rejected(tmp_path,monkeypatch):
    c,calls=camera(tmp_path,monkeypatch)
    monkeypatch.setattr(module,'image_info',lambda _:dict(width=8000,height=6000,sha256='same'))
    report=module.check_standard(c,count=3,report_path=tmp_path/'report.json')
    assert not report['passed'] and len(calls)==2 and 'Identical' in report['captures'][-1]['error']


def test_invalid_count_or_existing_report_does_not_open_camera(tmp_path):
    c=SimpleNamespace(capture=Mock())
    for count in [0,11,True]:
        with pytest.raises(ValueError):module.check_standard(c,count=count,report_path=tmp_path/'report.json')
    (tmp_path/'report.json').write_text('prior result')
    with pytest.raises(FileExistsError):module.check_standard(c,report_path=tmp_path/'report.json')
    c.capture.assert_not_called()


def test_corrupt_png_is_rejected_by_real_decoder(tmp_path):
    path=tmp_path/'invalid.png';path.write_bytes(b'not a PNG')
    with pytest.raises(ValueError,match='decoded'):module.image_info(path)


def test_camera_identity_change_is_not_a_successful_check(tmp_path,monkeypatch):
    c,calls=camera(tmp_path,monkeypatch);original=c.capture
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        if len(calls)==2:
            p=Path(result['metadata']);d=json.loads(p.read_text());d['device_id']='camera-B';p.write_text(json.dumps(d))
        return result
    c.capture=changed
    report=module.check_standard(c,count=3,report_path=tmp_path/'report.json')
    assert not report['passed'] and len(calls)==2 and 'Physical camera' in report['captures'][-1]['error']
