from pathlib import Path
import tempfile
import unittest

class ReceiverTrainingTests(unittest.TestCase):
    def test_refuses_overwriting_existing_report(self):
        from scripts.qlora.receive_training import audit_training
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); report=root/'report.json'; report.write_text('original')
            with self.assertRaisesRegex(ValueError,'REPORT_EXISTS'):
                audit_training(root,root,root,root,report)
            self.assertEqual(report.read_text(),'original')

    def test_missing_artifact_never_creates_success_report(self):
        from scripts.qlora.receive_training import audit_training
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); report=root/'report.json'
            with self.assertRaises((ValueError,FileNotFoundError)):
                audit_training(root,root,root,root,report)
            self.assertFalse(report.exists())

class ResumeBindingTests(unittest.TestCase):
    def fixture(self, root, changed=True):
        import torch
        from safetensors.torch import save_file
        from scripts.qlora.data import digest
        from scripts.qlora.runtime import write_json
        pilot=root/'pilot';resume=root/'resume'
        config={'learning_rate':0.0002}; manifest={'config_sha256':digest(config),'data_manifest_sha256':'d'*64}
        for folder,step in [(pilot,25),(resume,26)]:
            (folder/f'checkpoint-{step}').mkdir(parents=True)
            write_json(folder/'resolved-config.json',config)
            write_json(folder/'run-manifest.json',manifest)
            write_json(folder/'training-arguments.json',{'max_steps':50,'learning_rate':0.0002,'output_dir':str(folder),'logging_dir':str(folder/'log')})
            write_json(folder/'data-reference.json',{'dataset':'locked'})
            write_json(folder/f'checkpoint-{step}'/'binding.json',{**manifest,'global_step':step})
            write_json(folder/f'checkpoint-{step}'/'adapter_config.json',{'r':8,'target_modules':['q_proj','k_proj']})
        before=torch.zeros(2,2);after=torch.ones(2,2) if changed else before
        save_file({'weight':before},str(pilot/'checkpoint-25/adapter_model.safetensors'))
        save_file({'weight':after},str(resume/'checkpoint-26/adapter_model.safetensors'))
        write_json(resume/'adapter-update-report.json',{'adapter_delta_l2':2.0})
        return pilot,resume

    def test_positive_report_does_not_hide_unchanged_resume_weights(self):
        from scripts.qlora.receive_training import verify_resume_binding
        with tempfile.TemporaryDirectory() as tmp:
            pilot,resume=self.fixture(Path(tmp),changed=False)
            with self.assertRaisesRegex(ValueError,'RESUME_ACTUAL_UPDATE'):
                verify_resume_binding(pilot,resume)

    def test_config_or_learning_rate_drift_is_rejected(self):
        from scripts.qlora.receive_training import verify_resume_binding
        from scripts.qlora.runtime import write_json
        from scripts.qlora.data import read_json
        for name in ('resolved-config.json','training-arguments.json','checkpoint-26/binding.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                pilot,resume=self.fixture(Path(tmp)); data=read_json(resume/name)
                if name.endswith('binding.json'):data['config_sha256']='0'*64
                else:data['learning_rate']=0.1
                write_json(resume/name,data)
                with self.assertRaises(ValueError):verify_resume_binding(pilot,resume)

    def test_recomputes_finite_delta_from_actual_tensors(self):
        from scripts.qlora.receive_training import verify_resume_binding
        with tempfile.TemporaryDirectory() as tmp:
            pilot,resume=self.fixture(Path(tmp))
            self.assertEqual(verify_resume_binding(pilot,resume),{'changed_tensors':1,'adapter_delta_l2':2.0})

class ResumeParentTests(unittest.TestCase):
    def test_accepts_same_pinned_pilot_mounted_under_dataset_name(self):
        from scripts.qlora.receive_training import verify_resume_parent
        from scripts.qlora.assessment import PILOT_SHA
        root='/kaggle/input/datasets/member/private-input'
        verify_resume_parent(dict(resume_manifest_sha256=PILOT_SHA,resume_checkpoint=root+'/checkpoint-25'),
                             dict(pilot_manifest_sha256=PILOT_SHA,pilot=root))

    def test_rejects_other_parent_wrong_step_or_wrong_manifest(self):
        from scripts.qlora.receive_training import verify_resume_parent
        from scripts.qlora.assessment import PILOT_SHA
        context=dict(pilot_manifest_sha256=PILOT_SHA,pilot='/kaggle/input/correct')
        for path,sha in [('/kaggle/input/other/checkpoint-25',PILOT_SHA),('/kaggle/input/correct/checkpoint-26',PILOT_SHA),('/kaggle/input/correct/checkpoint-25','0'*64)]:
            with self.subTest(path=path,sha=sha),self.assertRaisesRegex(ValueError,'RESUME_PARENT'):
                verify_resume_parent(dict(resume_manifest_sha256=sha,resume_checkpoint=path),context)

if __name__=='__main__': unittest.main()
