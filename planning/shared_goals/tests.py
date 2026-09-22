from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.accounts.models import Account
from planning.goals.models import Goal
from planning.shared_goals.models import SharedGoal
from social.teams.models import Membership, Team


class SharedGoalFlowTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="shared-owner", email="shared-owner@example.com", password="TestPass2026!")
        self.member = User.objects.create_user(username="shared-member", email="shared-member@example.com", password="TestPass2026!")
        self.owner_account = Account.objects.create(owner=self.owner, name="Owner", currency="COP")
        self.member_account = Account.objects.create(owner=self.member, name="Member", currency="COP")
        self.team = Team.objects.create(owner=self.owner, name="Savings team", is_personal=False)
        Membership.objects.create(team=self.team, user=self.member, role="viewer", is_active=True)
        self.goal = Goal.objects.create(
            owner=self.owner,
            account=self.owner_account,
            name="Shared trip",
            target_amount="1000000.00",
            target_date=timezone.localdate() + timedelta(days=180),
        )

    def test_member_contribution_is_attributed_and_policy_can_restrict_it(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            "/api/planning/shared-goals/goals/",
            {"goal": self.goal.pk, "team": self.team.pk, "contribution_policy": "members"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        shared_id = created.data["id"]

        self.client.force_authenticate(self.member)
        contribution = self.client.post(
            "/api/planning/goals/aportes/",
            {
                "goal": self.goal.pk,
                "account": self.member_account.pk,
                "amount": "100000.00",
                "contributed_on": str(timezone.localdate()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-goal-member-001",
        )
        self.assertEqual(contribution.status_code, status.HTTP_201_CREATED, contribution.data)
        self.assertEqual(contribution.data["owner"], self.member.pk)
        self.goal.refresh_from_db()
        self.assertEqual(str(self.goal.progress), "100000.00")

        self.client.force_authenticate(self.owner)
        restricted = self.client.patch(
            f"/api/planning/shared-goals/goals/{shared_id}/",
            {"contribution_policy": "managers"},
            format="json",
        )
        self.assertEqual(restricted.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.member)
        denied = self.client.post(
            "/api/planning/goals/aportes/",
            {
                "goal": self.goal.pk,
                "account": self.member_account.pk,
                "amount": "100000.00",
                "contributed_on": str(timezone.localdate()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-goal-member-002",
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        projection = self.client.get(f"/api/planning/shared-goals/goals/{shared_id}/projection/")
        self.assertEqual(projection.status_code, status.HTTP_200_OK)
        self.assertTrue(SharedGoal.objects.get(pk=shared_id).is_active)
