"""
Task 3 tests (part 3): Popup manager (dashboard) and the public popup API (GET /site/api/popup/).
"""
import itertools
import shutil
import tempfile
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from campaigns.popup import get_eligible_popup, popup_target_url
from site_app.models import SitePopup

from .test_dashboard import DashboardBase, local, login, png
from .tests import add, make_campaign, make_product

_n = itertools.count(1)
API = "/site/api/popup/"


def make_popup(**kw):
    """A saved, active popup (the image file is a tiny PNG in a temp MEDIA_ROOT)."""
    kw.setdefault("title", f"Popup {next(_n)}")
    kw.setdefault("is_active", True)
    popup = SitePopup(**kw)
    popup.image_desktop.save("poster.png", png("poster.png"), save=False)
    popup.save()
    return popup


class MediaMixin:
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)


# ==========================================================================
# MANAGER (dashboard)
# ==========================================================================
class PopupManagerTests(MediaMixin, DashboardBase):
    def post(self, **over):
        data = {"title": f"Poster {next(_n)}", "link_type": "NONE", "button_text": "", "frequency": "ONCE_PER_SESSION",
                "pages": "HOME_ONLY", "priority": "0", "is_active": "1", "start_at": "", "end_at": "", "url": ""}
        files = over.pop("files", {"image_desktop": png("d.png")})
        data.update(over)
        return self.staff.post(reverse("popup_save"), {**data, **files})

    def test_list_page_and_modal_have_every_control_of_the_brief(self):
        html = self.staff.get(reverse("popup_list")).content.decode()
        for text in ("Create Popup", "Desktop image", "Mobile image", "Button text", "Once per browser session", "Once per day",
                     "Every visit", "Home page only", "All pages", "Priority", "Active", "Campaign page", "Product page",
                     "Any web address", "No link", "Starts", "Ends", "Preview", "pux-frame"):
            self.assertIn(text, html, text)

    def test_popup_list_uses_the_standard_table_markup(self):
        make_popup()
        html = self.staff.get(reverse("popup_list")).content.decode()
        for cls in ("product-table", "table-responsive white-space-nowrap", "table align-middle", "table-light"):
            self.assertIn(cls, html, cls)

    def test_create_a_popup_for_a_campaign(self):
        c = make_campaign(title="Black Friday")
        res = self.post(title="BF poster", link_type="CAMPAIGN", campaign=c.id, button_text="Shop now", priority="5",
                        frequency="ONCE_PER_DAY", pages="ALL_PAGES", files={"image_desktop": png("d.png"), "image_mobile": png("m.png")})
        self.assertTrue(res.json()["status"], res.content)
        p = SitePopup.objects.get()
        self.assertEqual((p.title, p.link_type, p.campaign, p.button_text, p.priority, p.frequency, p.pages, p.is_active),
                         ("BF poster", "CAMPAIGN", c, "Shop now", 5, "ONCE_PER_DAY", "ALL_PAGES", True))
        self.assertTrue(p.image_desktop and p.image_mobile)

    def test_schedule_is_saved_in_dhaka_time(self):
        self.post(start_at="2026-11-27T00:00", end_at="2026-11-30T23:59")
        p = SitePopup.objects.get()
        self.assertEqual(timezone.localtime(p.start_at).strftime("%Y-%m-%d %H:%M"), "2026-11-27 00:00")

    def test_link_target_validation(self):
        for link_type, message in (("CAMPAIGN", "Choose the campaign"), ("PRODUCT", "Choose the product"), ("URL", "Enter the web address")):
            res = self.post(link_type=link_type)
            self.assertEqual(res.status_code, 400, link_type)
            self.assertIn(message, res.json()["message"])
        self.assertEqual(self.post(link_type="URL", url="javascript:alert(1)").status_code, 400)
        self.assertEqual(self.post(link_type="URL", url="not a url").status_code, 400)
        self.assertEqual(SitePopup.objects.count(), 0)
        self.assertEqual(self.post(link_type="URL", url="https://example.com/sale").status_code, 200)
        self.assertEqual(self.post(link_type="URL", url="/campaign.html?slug=x").status_code, 200)

    def test_product_link_with_optional_campaign_prices(self):
        p = make_product(price=100)
        c = make_campaign()
        res = self.post(link_type="PRODUCT", product=p.id, campaign=c.id)
        self.assertTrue(res.json()["status"])
        popup = SitePopup.objects.get()
        self.assertEqual((popup.product, popup.campaign), (p, c))

    def test_other_validation(self):
        self.assertIn("title", self.post(title=" ").json()["message"].lower())
        self.assertIn("desktop image", self.post(files={}).json()["message"])
        self.assertIn("End time", self.post(start_at="2026-12-01T10:00", end_at="2026-12-01T09:00").json()["message"])
        self.assertIn("Priority", self.post(priority="high").json()["message"])
        bad = self.post(files={"image_desktop": __import__("django.core.files.uploadedfile", fromlist=["x"]).SimpleUploadedFile("x.png", b"nope", content_type="image/png")})
        self.assertEqual(bad.status_code, 400)

    def test_unknown_choices_fall_back_to_defaults(self):
        self.post(frequency="HACK", pages="HACK", link_type="HACK")
        p = SitePopup.objects.get()
        self.assertEqual((p.frequency, p.pages, p.link_type), ("ONCE_PER_SESSION", "HOME_ONLY", "NONE"))

    def test_edit_keeps_the_images_unless_replaced_and_can_clear_the_mobile_one(self):
        import os
        self.post(title="One", files={"image_desktop": png("d.png"), "image_mobile": png("m.png")})
        p = SitePopup.objects.get()
        old_desktop, old_mobile = p.image_desktop.path, p.image_mobile.path
        res = self.staff.post(reverse("popup_save"), {"id": p.id, "title": "Two", "link_type": "NONE", "frequency": "EVERY_VISIT",
                                                     "pages": "ALL_PAGES", "priority": "3", "is_active": "0"})
        self.assertTrue(res.json()["status"], res.content)
        p.refresh_from_db()
        self.assertEqual((p.title, p.frequency, p.is_active), ("Two", "EVERY_VISIT", False))
        self.assertTrue(os.path.exists(old_desktop) and os.path.exists(old_mobile))
        self.staff.post(reverse("popup_save"), {"id": p.id, "title": "Two", "link_type": "NONE", "clear_image_mobile": "1",
                                               "image_desktop": png("new.png", color="blue")})
        p.refresh_from_db()
        self.assertFalse(p.image_mobile)
        self.assertFalse(os.path.exists(old_mobile))
        self.assertFalse(os.path.exists(old_desktop))                 # replaced file is removed
        self.assertTrue(os.path.exists(p.image_desktop.path))

    def test_edit_form_data_endpoint(self):
        p = make_popup(title="Data", link_type="URL", url="https://x.com", button_text="Go", priority=4)
        data = self.staff.get(reverse("popup_data", args=[p.id])).json()["popup"]
        self.assertEqual((data["title"], data["link_type"], data["url"], data["priority"], data["button_text"]),
                         ("Data", "URL", "https://x.com", 4, "Go"))
        self.assertTrue(data["image_desktop"])

    def test_toggle_and_delete(self):
        p = make_popup()
        self.assertFalse(self.staff.post(reverse("popup_toggle", args=[p.id])).json()["is_active"])
        self.assertTrue(self.staff.post(reverse("popup_toggle", args=[p.id])).json()["is_active"])
        import os
        path = p.image_desktop.path
        self.assertTrue(self.staff.post(reverse("popup_delete", args=[p.id])).json()["status"])
        self.assertEqual(SitePopup.objects.count(), 0)
        self.assertFalse(os.path.exists(path))

    def test_list_shows_the_real_state_of_each_popup(self):
        now = timezone.now()
        live = make_popup(title="Showing")
        make_popup(title="Off", is_active=False)
        make_popup(title="Later", start_at=now + timedelta(days=1))
        make_popup(title="Over", end_at=now - timedelta(days=1))
        ended = make_campaign(start=now - timedelta(days=3), end=now - timedelta(days=1))
        make_popup(title="Dead link", link_type="CAMPAIGN", campaign=ended)
        res = self.staff.get(reverse("popup_list"))
        states = {r["p"].title: r["state"] for r in res.context["rows"]}
        self.assertEqual(states, {"Showing": "showing", "Off": "inactive", "Later": "scheduled", "Over": "ended", "Dead link": "skipped"})
        self.assertEqual(len(self.staff.get(reverse("popup_list"), {"status": "inactive"}).context["rows"]), 1)
        self.assertEqual(self.staff.get(reverse("popup_list"), {"q": "Showing"}).context["rows"][0]["p"], live)

    def test_a_customer_account_cannot_manage_popups(self):
        customer = login("customer")
        p = make_popup()
        for url in (reverse("popup_toggle", args=[p.id]), reverse("popup_delete", args=[p.id]), reverse("popup_save")):
            self.assertEqual(customer.post(url, {}).status_code, 403)
        self.assertEqual(customer.get(reverse("popup_data", args=[p.id])).status_code, 403)
        self.assertEqual(SitePopup.objects.count(), 1)


# ==========================================================================
# PUBLIC API (SPEC 10)
# ==========================================================================
class PopupAPITests(MediaMixin, TestCase):
    def get(self):
        res = Client().get(API)
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_nothing_eligible_returns_null_with_server_now(self):
        body = self.get()
        self.assertTrue(body["status"])
        self.assertIsNone(body["data"])
        self.assertIn("server_now", body)

    def test_payload_shape(self):
        p = make_popup(title="Hello", button_text="Shop now", priority=3, frequency="ONCE_PER_DAY", pages="ALL_PAGES")
        data = self.get()["data"]
        self.assertEqual(set(data), {"id", "title", "image_desktop", "image_mobile", "button_text", "link_type", "target_url",
                                     "frequency", "pages", "priority", "updated_at"})
        self.assertEqual((data["id"], data["title"], data["button_text"], data["frequency"], data["pages"], data["priority"]),
                         (p.id, "Hello", "Shop now", "ONCE_PER_DAY", "ALL_PAGES", 3))
        self.assertTrue(data["image_desktop"].startswith("http"))
        self.assertEqual(data["image_mobile"], data["image_desktop"])        # no mobile image: desktop is used
        self.assertIsNone(data["target_url"])                               # link_type NONE

    def test_mobile_image_is_returned_when_set(self):
        p = make_popup()
        p.image_mobile.save("m.png", png("m.png"), save=True)
        data = self.get()["data"]
        self.assertNotEqual(data["image_mobile"], data["image_desktop"])
        self.assertIn("/popup/mobile/", data["image_mobile"])

    def test_inactive_is_not_returned(self):
        make_popup(is_active=False)
        self.assertIsNone(self.get()["data"])

    def test_schedule_window(self):
        now = timezone.now()
        make_popup(title="future", start_at=now + timedelta(hours=1))
        make_popup(title="past", end_at=now - timedelta(hours=1))
        self.assertIsNone(self.get()["data"])
        make_popup(title="now", start_at=now - timedelta(hours=1), end_at=now + timedelta(hours=1))
        self.assertEqual(self.get()["data"]["title"], "now")

    def test_open_ended_schedules(self):
        now = timezone.now()
        make_popup(title="no end", start_at=now - timedelta(days=1))
        self.assertEqual(self.get()["data"]["title"], "no end")
        SitePopup.objects.all().delete()
        make_popup(title="no start", end_at=now + timedelta(days=1))
        self.assertEqual(self.get()["data"]["title"], "no start")

    def test_the_boundaries_are_inclusive(self):
        now = timezone.now()
        make_popup(title="edge", start_at=now, end_at=now)
        self.assertEqual(get_eligible_popup(now).title, "edge")

    def test_highest_priority_wins_then_the_newest(self):
        make_popup(title="low", priority=1)
        make_popup(title="high", priority=9)
        make_popup(title="mid", priority=5)
        self.assertEqual(self.get()["data"]["title"], "high")
        make_popup(title="high but newer", priority=9)
        self.assertEqual(self.get()["data"]["title"], "high but newer")

    def test_linked_to_a_draft_or_ended_campaign_is_skipped_for_the_next_popup(self):
        now = timezone.now()
        ended = make_campaign(start=now - timedelta(days=3), end=now - timedelta(days=1))
        draft = make_campaign(is_active=False)
        make_popup(title="fallback", priority=1)
        make_popup(title="ended link", priority=9, link_type="CAMPAIGN", campaign=ended)
        make_popup(title="draft link", priority=8, link_type="CAMPAIGN", campaign=draft)
        self.assertEqual(self.get()["data"]["title"], "fallback")

    def test_linked_to_a_live_or_upcoming_campaign_is_shown(self):
        now = timezone.now()
        live = make_campaign(title="Live One")
        make_popup(title="live link", priority=1, link_type="CAMPAIGN", campaign=live)
        self.assertEqual(self.get()["data"]["title"], "live link")
        SitePopup.objects.all().delete()
        upcoming = make_campaign(title="Soon", start=now + timedelta(days=1), end=now + timedelta(days=2))
        make_popup(title="upcoming link", link_type="CAMPAIGN", campaign=upcoming)
        self.assertEqual(self.get()["data"]["title"], "upcoming link")

    def test_the_skip_also_applies_to_a_product_popup_with_a_dead_campaign(self):
        now = timezone.now()
        ended = make_campaign(start=now - timedelta(days=3), end=now - timedelta(days=1))
        p = make_product()
        make_popup(title="dead", priority=9, link_type="PRODUCT", product=p, campaign=ended)
        make_popup(title="alive", priority=1)
        self.assertEqual(self.get()["data"]["title"], "alive")

    def test_a_popup_pausing_its_campaign_disappears_immediately(self):
        c = make_campaign()
        make_popup(link_type="CAMPAIGN", campaign=c)
        self.assertIsNotNone(self.get()["data"])
        c.is_active = False
        c.save()
        self.assertIsNone(self.get()["data"])

    def test_broken_links_are_not_shown(self):
        make_popup(title="no campaign", link_type="CAMPAIGN", campaign=None)
        make_popup(title="draft product", link_type="PRODUCT", product=make_product(status="Draft"))
        make_popup(title="no product", link_type="PRODUCT", product=None)
        self.assertIsNone(self.get()["data"])

    def test_popup_without_an_image_is_not_shown(self):
        SitePopup.objects.create(title="imageless", is_active=True, image_desktop="")
        self.assertIsNone(self.get()["data"])

    # ---- target URL ----
    def test_target_url_for_a_campaign(self):
        c = make_campaign(title="Black Friday")
        make_popup(link_type="CAMPAIGN", campaign=c)
        self.assertEqual(self.get()["data"]["target_url"], "/campaign.html?slug=black-friday")

    def test_target_url_for_a_product_in_the_linked_live_campaign_carries_the_campaign(self):
        c = make_campaign(title="Black Friday")
        p = make_product(name="Cradle Chair")
        add(c, p)
        make_popup(link_type="PRODUCT", product=p, campaign=c)
        self.assertEqual(self.get()["data"]["target_url"], "/product-details.html?slug=cradle-chair&campaign=black-friday")

    def test_target_url_for_a_product_without_campaign_pricing(self):
        c = make_campaign(title="Black Friday")
        member, outsider = make_product(name="In It"), make_product(name="Not In It")
        add(c, member)
        popup = make_popup(link_type="PRODUCT", product=outsider, campaign=c)
        self.assertEqual(popup_target_url(popup), "/product-details.html?slug=not-in-it")        # not in the campaign
        popup.campaign = None
        self.assertEqual(popup_target_url(popup), "/product-details.html?slug=not-in-it")        # no campaign chosen
        popup.product = member
        popup.campaign = c
        from campaigns.models import CampaignProduct
        CampaignProduct.objects.filter(campaign=c).update(is_active=False)
        self.assertEqual(popup_target_url(popup), "/product-details.html?slug=in-it")             # row switched off

    def test_target_url_for_a_custom_url_and_for_no_link(self):
        make_popup(title="custom", link_type="URL", url="https://example.com/offer", priority=2)
        make_popup(title="plain", link_type="NONE", priority=1)
        self.assertEqual(self.get()["data"]["target_url"], "https://example.com/offer")
        SitePopup.objects.filter(title="custom").delete()
        self.assertIsNone(self.get()["data"]["target_url"])

    def test_page_url_templates_can_be_configured(self):
        c = make_campaign(title="Black Friday")
        popup = make_popup(link_type="CAMPAIGN", campaign=c)
        with override_settings(CAMPAIGN_PAGE_URL="/campaigns/{slug}/"):
            self.assertEqual(popup_target_url(popup), "/campaigns/black-friday/")

    def test_updated_at_changes_when_the_popup_is_edited(self):
        p = make_popup()
        first = self.get()["data"]["updated_at"]
        p.title = "edited"
        p.save()
        self.assertNotEqual(self.get()["data"]["updated_at"], first)

    def test_the_popup_api_is_public(self):
        make_popup()
        self.assertEqual(Client().get(API).status_code, 200)             # no login needed
