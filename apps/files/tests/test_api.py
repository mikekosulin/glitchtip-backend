import os
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from model_bakery import baker

from glitchtip.test_utils.test_case import GlitchTipTestCase, GlitchTipTestCaseMixin

from ..models import File, FileBlob


def generate_file():
    im_io = BytesIO()
    return InMemoryUploadedFile(
        im_io, None, "random-name.jpg", "image/jpeg", len(im_io.getvalue()), None
    )


class ChunkUploadAPITestCase(GlitchTipTestCaseMixin, TestCase):
    def setUp(self):
        self.create_logged_in_user()
        self.url = reverse("api:get_chunk_upload_info", args=[self.organization.slug])

    def test_get(self):
        res = self.client.get(self.url)
        self.assertContains(res, self.organization.slug)

    def test_post(self):
        data = {"file_gzip": generate_file()}
        res = self.client.post(self.url, data)
        self.assertEqual(res.status_code, 200)


class ReleaseAssembleAPITests(GlitchTipTestCase):
    def setUp(self):
        self.create_user_and_project()
        self.organization.slug = "whab"
        self.organization.save()
        self.release = baker.make(
            "releases.Release", version="lol", organization=self.organization
        )
        self.url = reverse(
            "organization-releases-assemble",
            kwargs={
                "organization_slug": self.organization.slug,
                "version": self.release.version,
            },
        )

    def test_post(self):
        checksum = "e56191dcd7d54035f26f7dec999de2b1e4f10129"
        filename = "runtime-es2015.456e9ca9da400255beb4.js"
        map_filename = filename + ".map"
        zip_file = SimpleUploadedFile(
            checksum,
            open(os.path.dirname(__file__) + "/test_zip/" + checksum, "rb").read(),
        )
        FileBlob.objects.create(blob=zip_file, size=3635, checksum=checksum)
        res = self.client.post(self.url, {"checksum": checksum, "chunks": [checksum]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(File.objects.get(name=filename))
        map_file = File.objects.get(name=map_filename)
        self.assertTrue(map_file)
        self.assertTrue(map_file.releasefile_set.filter(release=self.release).exists())
