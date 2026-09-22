from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from finance.categories.models import Category


User = get_user_model()


class CategoriaIsolationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="category-owner",
            email="category-owner@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="category-other",
            email="category-other@example.com",
            password="test-password",
        )
        self.category = Category.objects.create(owner=self.user, name="Propia", type="expense")
        Category.objects.create(owner=self.other_user, name="Ajena", type="expense")
        self.client.force_authenticate(self.user)

    def test_list_only_returns_authenticated_owner_categories(self):
        response = self.client.get("/api/finance/categories/categorias/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.category.id])

    def test_create_assigns_owner_and_ignores_spoofed_owner(self):
        response = self.client.post(
            "/api/finance/categories/categorias/",
            {"name": "Nueva", "type": "income", "owner": self.other_user.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Category.objects.get(pk=response.data["id"])
        self.assertEqual(created.owner, self.user)

# Create your tests here.
