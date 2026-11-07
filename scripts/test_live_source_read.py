"""Current source ownership across independent checks and real file changes."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import live_source_read as sources
import production_workflow as workflow


class LiveSourceReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name).resolve()
        self.skill=self.base/'skill'
        self.studio=self.base/'studio'
        self.documents={'config/execution-routes.json':b'{"route":"synthetic"}\n',
                        'references/guide.md':b'Complete synthetic guide.\n'}
        self.dependencies=[]
        for path,raw in self.documents.items():
            c.atomic(self.skill/path,raw)
            self.dependencies.append({'space':'skill','path':path,'sha256':c.digest(raw),'size':len(raw)})
        raw=b'Synthetic prompt.\n'
        c.atomic(self.studio/'prompt.txt',raw)
        self.dependencies.append({'space':'studio','path':'prompt.txt','sha256':c.digest(raw),'size':len(raw)})

    def acquire(self):
        return sources.LiveSourceRead(self.studio,self.skill,self.dependencies)

    def test_route_and_dependency_checks_consume_one_acquired_source_set(self):
        with patch.object(sources,'stable_read',wraps=sources.stable_read) as read:
            owned=self.acquire()
            self.assertEqual(read.call_count,len(self.dependencies))
            for _ in range(3):
                for path,raw in self.documents.items():
                    self.assertEqual(owned.skill_bytes(path),raw)
                for dependency in self.dependencies:
                    self.assertEqual(workflow.current_sha256(self.studio,dependency,read=owned),dependency['sha256'])
            self.assertEqual(read.call_count,len(self.dependencies))
            (self.skill/'config/execution-routes.json').write_bytes(b'{"route":"changed"}\n')
            changed=self.acquire()
            self.assertEqual(read.call_count,len(self.dependencies)*2)
        self.assertNotEqual(changed.skill_bytes('config/execution-routes.json'),
                            owned.skill_bytes('config/execution-routes.json'))
        with self.assertRaisesRegex(ValueError,'not declared'):
            owned.skill_bytes('undeclared.txt')

    def test_a_source_file_link_cannot_replace_the_declared_input(self):
        source=self.skill/'references/guide.md'
        source.unlink()
        try:source.symlink_to(self.studio/'prompt.txt')
        except (OSError,NotImplementedError) as exc:self.skipTest(str(exc))
        owned=self.acquire()
        with self.assertRaisesRegex(ValueError,'symbolic link'):
            owned.skill_bytes('references/guide.md')

    def test_a_source_directory_link_is_rejected_before_reading_its_files(self):
        source=self.skill/'references'
        source.rename(self.skill/'original-references')
        try:source.symlink_to(self.skill/'original-references',target_is_directory=True)
        except (OSError,NotImplementedError) as exc:self.skipTest(str(exc))
        with patch.object(sources,'stable_read',wraps=sources.stable_read) as read:
            owned=self.acquire()
        self.assertNotIn(source/'guide.md',[call.args[0] for call in read.call_args_list])
        with self.assertRaisesRegex(ValueError,'symbolic link'):
            owned.skill_bytes('references/guide.md')

    def test_replacing_a_directory_during_acquisition_discards_its_values(self):
        original=sources.stable_read
        def replace_directory(selected,path):
            raw=original(selected,path)
            if path=='references/guide.md':
                selected.parent.rename(self.skill/'previous-references')
                selected.parent.mkdir()
                selected.write_bytes(raw)
            return raw
        with patch.object(sources,'stable_read',side_effect=replace_directory):
            owned=self.acquire()
        with self.assertRaisesRegex(ValueError,'directory changed'):
            owned.skill_bytes('references/guide.md')

    def test_unusual_directory_uses_the_existing_contained_path_check(self):
        original=sources._plain
        def unusual(path,*,directory):
            if directory and path==self.skill/'references':return None
            return original(path,directory=directory)
        with patch.object(sources,'_plain',side_effect=unusual),patch.object(c,'local',wraps=c.local) as local:
            owned=self.acquire()
        self.assertEqual(owned.skill_bytes('references/guide.md'),self.documents['references/guide.md'])
        self.assertIn((self.skill,'references/guide.md'),[call.args[:2] for call in local.call_args_list])

    def test_root_is_not_a_file_dependency(self):
        dependency={'space':'skill','path':'.'}
        owned=sources.LiveSourceRead(self.studio,self.skill,[dependency])
        with self.assertRaisesRegex(ValueError,'within its declared root'):
            owned.dependency(dependency)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
