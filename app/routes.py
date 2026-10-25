from flask import Blueprint, current_app, redirect, render_template, request, url_for

from . import db, links, paths, worker

bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET", "POST"])
def index():
    cfg = current_app.config
    form = {
        "links": "",
        "quality": cfg["DEFAULT_QUALITY"],
        "out_dir": cfg["DEFAULT_OUT_DIR"],
        "overwrite": False,
    }
    errors, line_errors = [], []

    if request.method == "POST":
        form["links"] = request.form.get("links", "")
        form["out_dir"] = request.form.get("out_dir", "")
        form["overwrite"] = "overwrite" in request.form

        try:
            form["quality"] = int(request.form.get("quality", ""))
        except ValueError:
            form["quality"] = None
        if form["quality"] not in cfg["QUALITIES"]:
            errors.append("Nieprawidłowa jakość.")
            form["quality"] = cfg["DEFAULT_QUALITY"]

        items, line_errors = links.parse_input(form["links"])
        if not items and not line_errors:
            errors.append("Podaj co najmniej jeden link lub ID filmu.")

        try:
            out_dir = paths.normalize_out_dir(form["out_dir"], cfg["DEFAULT_OUT_DIR"])
            paths.resolve_out_dir(cfg["OUTPUT_ROOT"], out_dir)
        except ValueError as e:
            errors.append(str(e))

        if not errors and not line_errors:
            db.create_job(db.get_db(), form["quality"], out_dir, form["overwrite"], items)
            worker.notify()
            return redirect(url_for(".jobs"))

    status = 400 if errors or line_errors else 200
    return render_template(
        "index.html", form=form, errors=errors, line_errors=line_errors, qualities=cfg["QUALITIES"]
    ), status


@bp.get("/jobs")
def jobs():
    conn = db.get_db()
    return render_template("jobs.html", jobs=db.recent_jobs(conn), active=db.has_active_items(conn))


@bp.get("/files")
def files():
    return render_template("files.html", videos=db.list_videos(db.get_db()))
