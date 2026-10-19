import importlib.util,pathlib,tempfile,unittest,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(path):
    spec=importlib.util.spec_from_file_location("under_test",ROOT/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
class CrimsonAssets(unittest.TestCase):
    def test_icon_manifests(self):
        m=load("scripts/apply_crimson_assets.py")
        self.assertEqual(m.icon_manifest("icon.png")["images"][1]["appearances"][0]["value"],"dark")
        self.assertEqual(m.preview_manifest()["images"][0]["filename"],"preview.png")
    def test_png_rejects_bad_file(self):
        m=load("scripts/apply_crimson_assets.py")
        with tempfile.TemporaryDirectory() as t:
            f=pathlib.Path(t)/"bad.png"
            f.write_bytes(b"wrong")
            with self.assertRaises(ValueError): m.png_ok(f)
    def test_reject_unsafe_archive(self):
        m=load("scripts/unpack_assets.py")
        with tempfile.TemporaryDirectory() as t:
            f=pathlib.Path(t)/"bad.zip"
            with zipfile.ZipFile(f,"w") as z:z.writestr("../bad","no")
            with self.assertRaises(ValueError):m.unpack(f,pathlib.Path(t)/"out")
    def test_repeated_source_patch(self):
        m=load("scripts/apply_crimson_assets.py")
        with tempfile.TemporaryDirectory() as t:
            base=pathlib.Path(t)
            src=base/"Nyxian"
            icon=src/"Nyxian/Assets.xcassets/Icons/AppIcon.appiconset"
            icon.mkdir(parents=True)
            proj=src/"Nyxian.xcodeproj/project.pbxproj"
            proj.parent.mkdir()
            proj.write_text('ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = "AppIcon Drawn Nyxcat Nyxcat2 Nyxcat3";')
            assets=base/"assets"
            assets.mkdir()
            image=b'\x89PNG\r\n\x1a\n'+b'\x00'*8+(1024).to_bytes(4,'big')*2+b'Z'*50
            for n in ("primary.png","alternate.png"):(assets/n).write_bytes(image)
            m.install(src,assets)
            m.install(src,assets)
            self.assertTrue((icon/"CrimsonPrimary.png").exists())
            self.assertIn("CrimsonAlternate",proj.read_text())
if __name__=="__main__":unittest.main()
