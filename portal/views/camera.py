from flask import flash, redirect, request
from flask_admin.contrib.sqla.filters import BaseSQLAFilter
from flask_admin import expose
from flask_admin.model.helpers import get_mdict_item_or_list
from flask_admin.form import rules
from flask_admin.helpers import is_form_submitted, validate_form_on_submit
from flask_security import current_user
from models.site import Site
from models.movie import Movie, MovieStatus
from models.camera import CameraConfig, Camera
from views.general import UserModelView
from views.elements.s3uploadfield import s3UploadFieldCameraConfig
from sqlalchemy import inspect
from math import sqrt


class FilterCameraConfigBySite(BaseSQLAFilter):
    # Override to create an appropriate query and apply a filter to said query with the passed value from the filter UI
    def apply(self, query, value, alias=None):
        return (
            query.join(CameraConfig.camera).join(Camera.site).filter(Site.id == value)
        )

    # readable operation name. This appears in the middle filter line drop-down
    def operation(self):
        return u"equals"

    # Override to provide the options for the filter - in this case it's a list of the titles of the Client model
    def get_options(self, view):
        return [(site.id, site.name) for site in Site.query.order_by(Site.name)]


class CameraConfigView(UserModelView):
    create_template = "cameraconfig/create.html"
    column_list = (
        "camera",
        CameraConfig.time_start,
        CameraConfig.time_end,
        CameraConfig.movie_setting_resolution,
        CameraConfig.movie_setting_fps,
    )
    column_filters = [FilterCameraConfigBySite(column=None, name="Site")]
    form_create_rules = ("camera",)

    form_extra_fields = {
        "file_name": s3UploadFieldCameraConfig(
            "File", allowed_extensions=("mkv", "mpeg", "mp4")
        )
    }

    def validate_form(self, form):
        if is_form_submitted():
            prevent_submit = False
            # Get list of all model attributes.
            mapper = inspect(CameraConfig)
            for column in mapper.attrs:
                # Check if model attribute is present in this form.
                if column.key != "time_end" and hasattr(form, column.key) and getattr(form, column.key) is not None:
                    # Check if data is set for this form field.
                    if getattr(form, column.key).data is None:
                        getattr(form, column.key).errors = ['Required']
                        prevent_submit = True

            # Check for max distance between ground control points.
            if hasattr(form, "gcps_dst_0_x") and getattr(form, "gcps_dst_0_x") is not None and not prevent_submit:
                gcps = []
                for i in range(4):
                    if hasattr(form, "gcps_dst_{}_x".format(i)) and hasattr(form, "gcps_dst_{}_y".format(i)):
                        gcps.append([float(getattr(form, "gcps_dst_{}_x".format(i)).data), float(getattr(form, "gcps_dst_{}_y".format(i)).data)])

                for i in range(len(gcps)):
                    for j in range(i + 1, len(gcps)):
                        distance = sqrt(pow(gcps[i][0] - gcps[j][0],2) + pow(gcps[i][1] - gcps[j][1],2))
                        if distance > 25:
                            flash("Distance between ground control points {} and {} is {:.1f} meters.".format(i+1, j+1, distance), "error")
                            return False

            if prevent_submit:
                return False

        return super(CameraConfigView, self).validate_form(form)

    @expose('/edit/', methods=('GET', 'POST'))
    def edit_view(self):
        id = get_mdict_item_or_list(request.args, 'id')
        model = self.get_one(id)
        movie = Movie.query.filter(Movie.config_id == model.id).order_by(Movie.id.desc()).first()
        if movie:
            self._template_args['movie'] = movie

            if movie.status == MovieStatus.MOVIE_STATUS_NEW or (model.gcps_src_0_x and not model.aoi_bbox):
                self.edit_template = 'cameraconfig/edit_waiting.html'
            elif model.aoi_bbox:
                self.form_edit_rules = (
                    "aoi_window_size",
                )
                self.edit_template = 'cameraconfig/edit_step3.html'
            else:
                self.form_edit_rules = (
                    "gcps_src_0_x",
                    "gcps_src_0_y",
                    "gcps_src_1_x",
                    "gcps_src_1_y",
                    "gcps_src_2_x",
                    "gcps_src_2_y",
                    "gcps_src_3_x",
                    "gcps_src_3_y",
                    "gcps_dst_0_x",
                    "gcps_dst_0_y",
                    "gcps_dst_1_x",
                    "gcps_dst_1_y",
                    "gcps_dst_2_x",
                    "gcps_dst_2_y",
                    "gcps_dst_3_x",
                    "gcps_dst_3_y",
                    "gcps_z_0",
                    "gcps_h_ref",
                    "corner_up_left_x",
                    "corner_up_left_y",
                    "corner_up_right_x",
                    "corner_up_right_y",
                    "corner_down_left_x",
                    "corner_down_left_y",
                    "corner_down_right_x",
                    "corner_down_right_y",
                    "lens_position_x",
                    "lens_position_y",
                    "lens_position_z",
                    "projection_pixel_size"
                )
                self.edit_template = 'cameraconfig/edit_step2.html'
        else:
            self.form_edit_rules = (
                "time_start",
                "time_end",
                "file_name",
            )
            self.edit_template = 'cameraconfig/edit_step1.html'

        self._form_edit_rules = rules.RuleSet(self, self.form_edit_rules)
        return super(CameraConfigView, self).edit_view()

    # Need this so the filter options are always up-to-date.
    @expose("/")
    def index_view(self):
        self._refresh_filters_cache()
        return super(CameraConfigView, self).index_view()

class CameraTypeView(UserModelView):
    def on_model_change(self, form, model, is_created):
        if is_created:
            model.user_id = current_user.id