from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from finance.vendors.models import Vendor


User = get_user_model()


class VendorIsolationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="vendor-owner",
            email="vendor-owner@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="vendor-other",
            email="vendor-other@example.com",
            password="test-password",
        )
        self.vendor = Vendor.objects.create(owner=self.user, name="Comercio propio")
        self.other_vendor = Vendor.objects.create(owner=self.other_user, name="Comercio ajeno")
        self.client.force_authenticate(self.user)

    def test_list_and_detail_are_scoped_to_authenticated_owner(self):
        response = self.client.get("/api/finance/vendors/proveedores/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.vendor.id])
        hidden = self.client.get(f"/api/finance/vendors/proveedores/{self.other_vendor.id}/")
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_assigns_owner_and_ignores_spoofed_owner(self):
        response = self.client.post(
            "/api/finance/vendors/proveedores/",
            {"name": "Nuevo comercio", "owner": self.other_user.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Vendor.objects.get(pk=response.data["id"]).owner, self.user)

# Create your tests here.
