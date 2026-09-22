from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.accounts.models import Account
from planning.goals.models import Goal, GoalContribution, GoalDomainEventOutbox, GoalMilestone


User = get_user_model()


class GoalIsolationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="goal-owner",
            email="goal-owner@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="goal-other",
            email="goal-other@example.com",
            password="test-password",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta propia")
        self.other_account = Account.objects.create(owner=self.other_user, name="Cuenta ajena")
        self.goal = Goal.objects.create(
            owner=self.user,
            account=self.account,
            name="Meta propia",
            target_amount="1000000.00",
            target_date=timezone.localdate() + timedelta(days=30),
        )
        Goal.objects.create(
            owner=self.other_user,
            account=self.other_account,
            name="Meta ajena",
            target_amount="2000000.00",
            target_date=timezone.localdate() + timedelta(days=60),
        )
        self.client.force_authenticate(self.user)

    def test_list_only_returns_authenticated_owner_goals(self):
        response = self.client.get("/api/planning/goals/metas/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [self.goal.id])

    def test_create_assigns_owner_and_rejects_foreign_account(self):
        payload = {
            "name": "Meta nueva",
            "target_amount": "500000.00",
            "target_date": str(timezone.localdate() + timedelta(days=90)),
            "account": self.other_account.id,
            "owner": self.other_user.id,
        }
        rejected = self.client.post("/api/planning/goals/metas/", payload, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account", rejected.data)

        payload["account"] = self.account.id
        created = self.client.post("/api/planning/goals/metas/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        goal = Goal.objects.get(pk=created.data["id"])
        self.assertEqual(goal.owner, self.user)
        self.assertEqual(goal.progress, 0)
        self.assertEqual(goal.status, Goal.Status.ACTIVE)

    def test_progress_and_status_cannot_be_written_through_goal_api(self):
        response = self.client.patch(
            f"/api/planning/goals/metas/{self.goal.id}/",
            {
                "progress": "999999.00",
                "status": Goal.Status.COMPLETED,
                "active": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.progress, 0)
        self.assertEqual(self.goal.status, Goal.Status.ACTIVE)
        self.assertTrue(self.goal.active)

    def test_contribution_is_idempotent_and_completes_goal(self):
        payload = {
            "goal": self.goal.id,
            "account": self.account.id,
            "amount": "1000000.00",
            "contributed_on": str(timezone.localdate()),
            "note": "Aporte de cierre",
        }

        created = self.client.post(
            "/api/planning/goals/aportes/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="goal-test-contribution-001",
        )
        replay = self.client.post(
            "/api/planning/goals/aportes/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="goal-test-contribution-001",
        )

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertEqual(created.data["id"], replay.data["id"])
        self.assertEqual(GoalContribution.objects.filter(goal=self.goal).count(), 1)
        self.goal.refresh_from_db()
        self.assertEqual(str(self.goal.progress), "1000000.00")
        self.assertEqual(self.goal.status, Goal.Status.COMPLETED)
        self.assertFalse(self.goal.active)
        self.assertIsNotNone(self.goal.completed_at)
        self.assertTrue(
            GoalDomainEventOutbox.objects.filter(
                event_type="goals.contribution.recorded.v1"
            ).exists()
        )

    def test_reversing_contribution_reopens_completed_goal(self):
        created = self.client.post(
            "/api/planning/goals/aportes/",
            {
                "goal": self.goal.id,
                "account": self.account.id,
                "amount": "1000000.00",
                "contributed_on": str(timezone.localdate()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="goal-test-contribution-002",
        )

        reversed_response = self.client.post(
            f"/api/planning/goals/aportes/{created.data['id']}/reverse/",
            {"reason": "Aporte registrado por error"},
            format="json",
        )

        self.assertEqual(reversed_response.status_code, status.HTTP_200_OK)
        self.goal.refresh_from_db()
        self.assertEqual(str(self.goal.progress), "0.00")
        self.assertEqual(self.goal.status, Goal.Status.ACTIVE)
        self.assertTrue(self.goal.active)
        self.assertIsNone(self.goal.completed_at)

    def test_contribution_rejects_foreign_goal_and_requires_idempotency_key(self):
        foreign_goal = Goal.objects.get(owner=self.other_user)
        payload = {
            "goal": foreign_goal.id,
            "amount": "100.00",
            "contributed_on": str(timezone.localdate()),
        }
        foreign = self.client.post(
            "/api/planning/goals/aportes/",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY="goal-test-foreign-001",
        )
        missing_key = self.client.post(
            "/api/planning/goals/aportes/",
            {**payload, "goal": self.goal.id},
            format="json",
        )

        self.assertEqual(foreign.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("goal", foreign.data)
        self.assertEqual(missing_key.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", missing_key.data)

    def test_goal_lifecycle_uses_explicit_actions(self):
        paused = self.client.post(f"/api/planning/goals/metas/{self.goal.id}/pause/", {}, format="json")
        resumed = self.client.post(f"/api/planning/goals/metas/{self.goal.id}/resume/", {}, format="json")
        canceled = self.client.post(
            f"/api/planning/goals/metas/{self.goal.id}/cancel/",
            {"reason": "Cambio de estrategia financiera"},
            format="json",
        )

        self.assertEqual(paused.status_code, status.HTTP_200_OK)
        self.assertEqual(paused.data["status"], Goal.Status.PAUSED)
        self.assertEqual(resumed.status_code, status.HTTP_200_OK)
        self.assertEqual(resumed.data["status"], Goal.Status.ACTIVE)
        self.assertEqual(canceled.status_code, status.HTTP_200_OK)
        self.assertEqual(canceled.data["status"], Goal.Status.CANCELED)

    def test_milestone_and_projection_follow_contribution_history(self):
        milestone = self.client.post(
            "/api/planning/goals/milestones/",
            {"goal": self.goal.pk, "name": "Half way", "target_amount": "500000.00"},
            format="json",
        )
        self.assertEqual(milestone.status_code, status.HTTP_201_CREATED)
        self.client.post(
            "/api/planning/goals/aportes/",
            {
                "goal": self.goal.pk,
                "account": self.account.pk,
                "amount": "600000.00",
                "contributed_on": str(timezone.localdate()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="goal-milestone-contribution-001",
        )
        row = GoalMilestone.objects.get(pk=milestone.data["id"])
        self.assertIsNotNone(row.achieved_at)
        projection = self.client.get(f"/api/planning/goals/metas/{self.goal.pk}/projection/")
        self.assertEqual(projection.status_code, status.HTTP_200_OK)
        self.assertEqual(projection.data["status"], "projected")
        self.assertIn("projected_completion_date", projection.data)

# Create your tests here.
