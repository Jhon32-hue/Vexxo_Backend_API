from django.contrib import admin

from finance.vendors.models import Vendor, VendorAlias


admin.site.register(Vendor)
admin.site.register(VendorAlias)
