# author: @sopier
from flask import render_template, request, redirect, send_from_directory, session, flash, url_for
from flask import make_response # untuk sitemap
from app import app
# untuk find_one based on data id => db.freewaredata.find_one({'_id': ObjectId(file_id)})
# atom feed
from werkzeug.contrib.atom import AtomFeed
from bson.objectid import ObjectId 
from filters import slugify, splitter, onlychars, get_first_part, get_last_part, formattime, cleanurl
from functools import wraps
from forms import AdminLoginForm, UserLoginForm, UserRegisterForm
import datetime
import pymongo
from flask.ext.mail import Message, Mail
import random
import os
import urllib2
from bs4 import BeautifulSoup
import re
from urllib import unquote
from ConfigParser import SafeConfigParser
import sys


# setup database mongo
c = pymongo.Connection()
dbentity = c["entities"]  # nanti ada dbentity.user, dbentity.admin, dll


@app.template_filter()
def slug(s):
    """ 
    transform words into slug 
    usage: {{ string|slug }}
    """
    return slugify(s)


@app.template_filter("humanize")
def jinja2_filter_humanize(date):
    """
    convert datetime object into human readable
    usage humanize(dateobject) or if in template
    {{ dateobject|humanize }}
    """
    import humanize
    secs = datetime.datetime.now() - date
    secs = int(secs.total_seconds())
    date = humanize.naturaltime(datetime.datetime.now() - datetime.timedelta(seconds=secs))  # 10 seconds ago
    return date


@app.template_filter("get_first_word")
def jinja2_filter_get_first_word(sentence):
    """
    get only the first word from long sentence
    ex: kholid fuadi => kholid
    """
    return sentence.split()[0]


@app.route("/thumb/<year>/<month>/<day>/<file_path>")
def get_thumb_assets(year, month, day, file_path):
    """
    get marketplace assets
    """
    app_folder = os.getcwd()  # ~/git/manus2
    asset_folder = os.path.join(app_folder, "assets")
    fpath = os.path.join(year, month, day, file_path)

    return send_from_directory(asset_folder, fpath)


# handle robots.txt file
@app.route("/robots.txt")
def robots():
    # point to robots.txt files
    return send_from_directory(app.static_folder, request.path[1:])


def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("admin") is not None:
            return f(*args, **kwargs)
        else:
            flash("Please log in first...", "error")
            next_url = request.url
            login_url = "%s?next=%s" % (url_for("admin_login"), next_url)
            return redirect(login_url)
    return decorated_function


def user_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("username") is not None:
            return f(*args, **kwargs)
        else:
            flash("Please log in first...", "error")
            next_url = request.url
            login_url = "%s?next=%s" % (url_for("users_login"), next_url)
            return redirect(login_url)
    return decorated_function


@app.route("/")
def index():
    """
    halaman index nanti diambilkan data secara random (experiment)
    """
    # data
    docdb = c["pdfs"]

    # coba
    terms = c["terms"]

    # coba-coba
    skip_number = random.randint(0, terms.term.find().count() - 10)
    datacoba = terms.term.find().skip(skip_number).limit(10)

    # find data which has thumbnail and sort it
    skip_number = random.randint(0, docdb.pdf.find({"thumb_updated": {"$exists": True}}).count() - 10)
    # data = [doc for doc in docdb.pdf.find().skip(skip_number).limit(10)]
    # data = [doc for doc in docdb.pdf.find().limit(10)]
    # data = [doc for doc in docdb.pdf.find({"thumb_updated": {"$exists": True}}).skip(skip_number).limit(10)]
    data = [doc for doc in docdb.pdf.find({"thumb_updated": {"$exists": True}}).sort("added", -1).limit(10)]
    # data = [doc for doc in docdb.pdf.find().sort("_id", -1).limit(10)]
    # print data

    # creating fake updated data
    import humanize
    for d in data:
        d["updated"] = humanize.naturaltime(datetime.datetime.now() - datetime.timedelta(seconds=random.randint(0, 600)))
        # optional thumbnail
        # jika ada key thumbnail:
        # thumbnail = True
        # else
        # thumbnail = False
        d["thumbnail"] = False

    return render_template("index.html", data=data,datacoba=datacoba)


@app.route("/page/<int:num>")
def index_paging(num):
    # redirect to hompage if num == 1
    if num == 1:
        return redirect("/", 301)

    # get data based on index
    docdb = c["pdfs"]

    # per page == 10
    per_page = 10

    # skipped
    skipped = per_page * (num - 1)

    # detect last page
    last_page = False
    thumb_data_count = docdb.pdf.find({"thumb_updated": {"$exists": True}}).count()

    if (thumb_data_count / 10) + 1 == int(num):
        # we are on last page
        last_page = True

    print

    data = [doc for doc in docdb.pdf.find({"thumb_updated": {"$exists": True}}).sort("added", -1).skip(skipped).limit(10)]
    return render_template("index_paging.html", data=data, num=num, last_page=last_page)


#@app.route("/<first_word>/<full_word>")
#def search(first_word, full_word):
#    """
#    ini diganti aja, rawan banned kaya
#    """
#    docdb = c["pdfs"]
#    data_raw = docdb.command("text", "pdf", search=full_word, limit=10)
#    results_count = data_raw["stats"]["nscanned"]
#    data = [d["obj"] for d in data_raw["results"]]
#
#    # creating fake updated data
#    import humanize
#    for d in data:
#        d["updated"] = humanize.naturaltime(datetime.datetime.now() - datetime.timedelta(seconds=random.randint(0, 600)))
#
#    # building related data
#    terms = c["terms"]
#    related_data = terms.command("text", "term", search=full_word, limit=10)
#    related_data = [d["obj"] for d in related_data["results"]]
#
#    return render_template("search.html", data=data, keyword=full_word,
#                           results_count=results_count, related_data=related_data)


@app.route("/tags/<tag>")
def suggested_tags(tag):
    """
    buat halaman tags yang isinya search term
    dari onkeywords.com, adwords, ubersuggests dan sejenisnya
    """
    pdfdb = c["pdfs"]
    tagsdb = c["pdfterms"]
    terms = c["terms"]

    # prevent keyword injection
    kwrd = tagsdb.term.find_one({"term": tag.replace("-", " ")})
    if not kwrd:
        return redirect("/", 301)

    tag = tag.replace("-", " ")
    data = pdfdb.command("text", "pdf", search=tag, limit=10)
    results_count = data["stats"]["nscanned"]

    # ini harusnya prioritas nyari yang ada thumbnailnya dulu
    # piye carane yo????
    data = [d["obj"] for d in data["results"]]

    # building related data

    related_data = terms.command("text", "term", search=tag, limit=10)
    related_data = [d["obj"] for d in related_data["results"]]

    ## on-page seo
    # 1. related tags for meta desc
    meta_desc = ", ".join([d["term"] for d in related_data][:5])
    # 2. meta keywords, ambil dari tag, split, join
    meta_key = ", ".join([t for t in tag.split(" ") if len(t) > 3])
    # 3. meta key tags with get rid off short word
    meta_key_tags = [t for t in tag.split(" ")[:5] if len(t) > 3]
    # 4. fake category?
    meta_key_cat = tag.split(" ")[0]

    # get tags suggestion to enrich index and strengthen onpage seo

    tags = tagsdb.command("text", "term", search=tag)
    tags = [d["obj"] for d in tags["results"]]
    random.shuffle(tags)
    tags = tags[:5]

    return render_template("tags.html", data=data, tag=tag, results_count=results_count,
                           related_data=related_data, tags=tags, meta_desc=meta_desc,
                          meta_key=meta_key, meta_key_tags=meta_key_tags, meta_key_cat=meta_key_cat)


@app.route("/read/<oid>/<title>", methods=["GET", "POST"])
def reader(oid, title):
    """
    PDF reader using google docs preview
    """
    docdb = c["pdfs"]
    data = docdb.pdf.find_one({"_id": ObjectId(oid)})

    # get tags suggestion to enrich index and strengthen onpage seo
    tagsdb = c["pdfterms"]
    tags = tagsdb.command("text", "term", search=title, limit=20)
    tags = [d["obj"] for d in tags["results"]]
    random.shuffle(tags)
    tags = tags[:10]


    return render_template("reader.html", data=data, tags=tags)


@app.route("/view/<oid>")
def view_url(oid):
    """
    redirect to original link
    """
    docdb = c["pdfs"]
    data = docdb.pdf.find_one({"_id": ObjectId(oid)})
    return redirect(data["url"])


@app.route("/download/<title>")
def download(title):
    """
    redirect to ad-center landing page
    """
    return redirect("http://ads.ad-center.com/offer?prod=101&ref=4988911&q=" + title.replace("-", " ").title())


@app.route("/users-add-collection", methods=["POST"])
@user_login_required
def users_add_collection():
    """
    adding favorites books to users collection
    """
    if request.method == "POST":
        dbentity = c["entities"]
        oid = request.form["oid"]
        # jika ada key favorited
        if dbentity.users.find_one({"username": session["username"]}).has_key("favorited"):
            # jika oid tidak ada di favorited,
            if oid not in dbentity.users.find_one({"username": session["username"]})["favorited"]:
                # tambahkan oid ke favorited
                dbentity.users.update({"username": session['username']}, {"$push": {"favorited": oid}})
        else:  # user ini belum punya favorited key (user baru kinyis2)
            dbentity.users.update({"username": session['username']}, {"$push": {"favorited": oid}})

        return "sukses %s" % oid


@app.route("/add-comment", methods=["POST"])
@user_login_required
def user_add_comment():
    pdfdb = c["pdfs"]
    if request.method == "POST":
        oid = request.form["oid"]
        text = request.form["text"]
        print session
        username = session["username"]
        # input into dbase => home => comments => []
        pdfdb.pdf.update({"_id": ObjectId(oid)}, {"$push": {"comments": {"username": username, "text": text, "added": datetime.datetime.now()}}})
        return "sukses %s %s by %s" % (text, oid, username)


@app.route("/report-abuse", methods=["POST"])
@user_login_required
def report_abuse():
    admindb = c["admindb"]
    if request.method == "POST":
        # insert url to the admindb.abuse
        oid = request.form["oid"]
        title = request.form["title"]
        added = datetime.datetime.now()
        url = "/read/%s/%s" % (oid, title)
        if admindb.abuse.find_one({"url": url}) is None:
            admindb.abuse.insert({"url": url, "added": added})
        return "sukses %s" % url


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]
        return "sukses %s %s %s" % (name, email, message)
    return render_template("contact.html")


@app.route("/disclaimer")
def disclaimer():
    """
    disclaimer page
    """
    return render_template("disclaimer.html")


@app.route("/admin")
@admin_login_required
def admin():
    return render_template("admin/index.html")


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_login_required
def admin_settings():
    parser = SafeConfigParser()
    settings_path = os.path.join(os.getcwd(), "app", "settings.ini")
    parser.read(settings_path)

    if request.method == "POST":
        # save global settings
        url = request.form["url"]
        name = request.form["name"]
        # update settings.ini file
        url = parser.set("site_config", "url", url)
        name = parser.set("site_config", "name", name)
        with open(settings_path, "w") as f:
            parser.write(f)
        return "sukses"

    url = parser.get("site_config", "url")
    name = parser.get("site_config", "name")
    data = {"name": name, "url": url}
    return render_template("admin/admin_settings.html", data=data)


@app.route("/admin/filter")
@admin_login_required
def admin_filter():
    """
    - ambil data search terms dari dbase :: terms.term.find().limit(100)
    - tampilkan dalam bentuk tabel
    - pilih search term yang mau di post
    - cari variasi keyword lain dari search term tadi di bing
    - post!
    """
    terms = c["terms"]
    skip_number = random.randint(0, terms.term.find().count() - 10)
    # try to find all keywords with status 0
    try:
        data = terms.term.find().skip(skip_number).limit(10)
    except:
        # show random term inputan lama yang tidak ada status nye
        data = terms.term.find().skip(skip_number).limit(10)
    # show latest term
    # data = dbterms.term.find().sort("_id", -1).limit(10)
    # jumlah data
    data_count = terms.term.find().count()
    return render_template("admin/admin_filter.html", data=data, data_count=data_count)


@app.route("/admin/filter/<keyword>")
@admin_login_required
def admin_filter_by_keyword(keyword):
    """
    search full text field term
    biar mempercepat kerjaan
    """
    terms = c["terms"]
    # skip_number = random.randint(0, terms.term.find().count() - 10)
    data = terms.command("text", "term", search=keyword, filter={"status": None}, limit=10)
    data_count = terms.command("text", "term", search=keyword, filter={"status": None})["stats"]
    data = [d["obj"] for d in data["results"]]
    return render_template("admin/admin_filter_by_keyword.html", data=data, keyword=keyword, data_count=data_count)


# admin_poster support
# 1. find related keyword di Bing
# 2. find related keyword di Google
@app.route("/admin/find_related_keyword/<search_engine>", methods=["POST"])
@admin_login_required
def find_related_keyword(search_engine):
    """
    @return list of related keywords from search engine
    """
    if request.method == "POST":
        if search_engine == "google":  # find related keywords di Google
            return "Pencarian keyword di %s sukses" % search_engine
        elif search_engine == "bing":
            return "Pencarian keyword di %s sukses" % search_engine


@app.route("/admin/delete_keyword", methods=["POST"])
@admin_login_required
def delete_keyword():
    if request.method == "POST":
        terms = c["terms"]
        oid = request.form["oid"]
        terms.term.remove({"_id": ObjectId(oid)})
        return "sukses deleting keyword with id: %s" % oid


@app.route("/admin/insert", methods=["POST"])
@admin_login_required
def insert_keyword():
    if request.method == "POST":
        pdfterms = c["pdfterms"]
        term = request.form["term"]
        if not pdfterms.term.find_one({"term": term}):
            pdfterms.term.insert({"term": term})
        # update terms document status dari 0 => 1
        terms = c["terms"]
        terms.term.update({"term": term}, {"$set": {"status": 1}})
        return "sukses inserting term: %s" % term


@app.route("/admin/insert-all", methods=["POST"])
@admin_login_required
def insert_keywords():
    terms = c["terms"]
    pdfterms = c["pdfterms"]

    if request.method == "POST":
        terms = request.form.getlist("terms[]")
        print request.form
        for term in terms:
            print term
            if not pdfterms.term.find_one({"term": term}):
                pdfterms.term.insert({"term": term})
            # update terms document status dari 0 => 1
            terms.term.update({"term": term}, {"$set": {"status": 1}})
        return "sukses inserting all terms"


@app.route("/admin/keywords")
@admin_login_required
def list_keyword():
    pdfterms = c["pdfterms"]
    data = pdfterms.term.find().sort("_id", -1).limit(10)
    data_count = pdfterms.term.find().count()
    return render_template("admin/admin_keyword.html", data=data, data_count=data_count)


@app.route("/admin/keyword-injector", methods=["GET", "POST"])
@admin_login_required
def mass_keyword_injector():
    """
    get keyword from onkeywords.com
    then inject them!
    this is to hinder quick google banned
    and filter bad keywords (lendir)
    """
    if request.method == "POST":
        # get keywords from textarea
        # split lines
        # if not on database pdfterms.term, inject them!
        cleantermdb = c["pdfterms"]
        # note: database ini adalah database yang bersih, bebas dari lendir dan keyword2 jelek lain
        keywords = request.form["keywords"].splitlines()
        for keyword in keywords:
            if keyword:
                if cleantermdb.term.find_one({"term": keyword}) is None:
                    cleantermdb.term.insert({"term": keyword})
        return "sukses %s" % keywords

    return render_template("admin/admin_keyword_injector.html")


@app.route("/admin/thumbnailer", methods=["GET", "POST"])
@app.route("/admin/thumbnailer/<term>", methods=["GET", "POST"])
@admin_login_required
def thumbnailer(term=None):
    # data
    docdb = c["pdfs"]
    # randomize the skip
    skip_number = random.randint(0, docdb.pdf.find().count() - 10)
    data = docdb.pdf.find({"thumb_updated": {"$exists": False}}).skip(skip_number).limit(10)
    # data = docdb.pdf.find().limit(10)

    if term is not None:
        # cari berdasarkan keyword $and berdasar thumb_updated == false
        # pakai regex aja, sebenere yang lebih pas pake ful text, biar bisa search di-url juga :(
        pattern = re.compile(".*" + term + ".*")
        # data = docdb.pdf.find({"$and": [{"thumb_updated": {"$exists": False}}, {"title": pattern}]}).limit(10)
        data = docdb.command("text", "pdf", search=term, limit=15)
        data = [d["obj"] for d in data["results"] if "thumb_updated" not in d["obj"].viewkeys()]  # harusnya cari yang belum ada field thumb_updated

    if request.method == "POST":
        oid = request.form["oid"]
        url = request.form["url"]
        title = request.form["title"]

        # buat folder path dulu
        # simpan di folder dgn format => thn/bln/tanggal
        # app folder
        app_folder = os.getcwd()
        # get year/month/date
        date_folder = datetime.datetime.now().strftime("%Y/%m/%d")
        # joined both
        full_folder_path = os.path.join(app_folder, "assets", date_folder)  # ~/path_to_app/assets/2014/11/09/fname.jpg
        # create folder if not exists
        if not os.path.exists(full_folder_path):
            os.makedirs(full_folder_path)

        img_filename = "%s-%s.png" % (oid, slugify(title))

        # full file path
        full_file_path = os.path.join(full_folder_path, img_filename)

        # download the thumbnail
        imgstr = urllib2.urlopen(url).read()

        with open(full_file_path, "w") as f:
            f.write(imgstr)

        # update database => 1. thumb_url: lokasi ke gambar 2. thumb_updated: terakhir update
        # nanti di halaman index, tampilkan data yang ada thumb_updated saja
        fpath = os.path.join(date_folder, img_filename)
        docdb.pdf.update({"_id": ObjectId(oid)}, {"$set": {"added": datetime.datetime.now(), "fpath": fpath, "thumb_updated": datetime.datetime.now()}})
        return "sukses %s %s" % (oid, url)

    return render_template("admin/admin_thumbnailer.html", data=data)


@app.route("/admin/pinger", methods=["GET", "POST"])
def pinger():
    # dbase
    dbping = c["ping"]
    data = dbping.ping.find_one()
    if data is None:
        data = dbping.ping.insert({"actor": "admin", "last_ping": datetime.datetime.now()})

    if request.method == "POST":
        # ping goes here
        import urlparse
        import urllib
        import urllib2
        google_ping_url = "http://www.google.com/webmasters/sitemaps/ping?sitemap="
        # domain_url = app.config["WEB_URL"]
        domain_url = "http://127.0.0.1"
        sitemap_url = "/sitemap"

        # build url
        url = urlparse.urljoin(domain_url, sitemap_url)
        url = google_ping_url + url
        # execute
        r = urllib2.urlopen(urllib.unquote_plus(url))

        # update database records
        dbping.ping.update({"actor": "admin"}, {"$set": {"last_ping": datetime.datetime.now()}})

        return r.msg

    return render_template("admin/admin_pinger.html", data=data)


@app.route("/admin/grabber", methods=["GET", "POST"])
def grabber():
    """
    isinya ngambil logic yang dari googlepy
    nama fungsi: grab(url)
    """
    pdfdb = c["pdfs"]
    if request.method == "POST":
        keyword = request.form["keyword"]
        data = pdfdb.pdf.find_one({"keyword": keyword})
        # cek di database apakah keyword tsb sudah ada?
        if data is not None:
            return "null"  # ini berarti sudah ada keyword yang ingin dicari, kembalikan lagi ke template, kasih alert apa kek
        else:
            # built url
            url = "https://www.google.com/search?q=%s+filetype:pdf&num=10" % keyword.replace(" ", "+")
            # insert into database
            # return "%s" % grab(url)
            data = grab(url)
            for d in data:
                d["added"] = datetime.datetime.now()
                d["keyword"] = keyword
                pdfdb.pdf.insert(d)
            return "%s" % data
        # return "sukses %s" % keyword
    count = pdfdb.pdf.find().count()
    return render_template("admin/admin_grab.html", count=count)


@app.route("/admin/open-directory-grabber", methods=["GET", "POST"])
@admin_login_required
def open_directory_grabber():
    """
    grab and parse url which contains pdf list
    """
    import urllib2
    from urlparse import urljoin
    import re
    import json

    if request.method == "POST":
        url = request.form["url"]
        opener = urllib2.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        html = opener.open(url).read()
        # html = urllib2.urlopen(url).read()
        urls = re.findall("href=\"(.*\.pdf)\"", html)
        urls = [urljoin(url, u) for u in urls]
        return json.dumps(urls)
    return render_template("admin/admin_open_directory_grabber.html")


@app.route("/admin/open-directory-data-insert", methods=["POST"])
@admin_login_required
def open_directory_data_insert():
    """
    for inserting data after grabbing open directory
    dbase used => pdfs.pdf

    field: {added, keyword, title, url, snippet, thumb_updated, fpath}

    1. downloading image
    2. inserting data from fields

    """
    if request.method == "POST":
        added = datetime.datetime.now()
        title = request.form["title"]
        snippet = request.form["snippet"]
        url = request.form["url"]
        keyword = title

        # insert database dengan 5 data di atas
        pdfdb = c["pdfs"]
        oid = pdfdb.pdf.insert({
                "added": added,
                "title": title,
                "snippet": snippet,
                "url": url,
                "keyword": keyword,
            })
        print "sukses"

        # buat folder path dulu
        # simpan di folder dgn format => thn/bln/tanggal
        # app folder
        app_folder = os.getcwd()
        # get year/month/date
        date_folder = datetime.datetime.now().strftime("%Y/%m/%d")
        # joined both
        full_folder_path = os.path.join(app_folder, "assets", date_folder)  # ~/path_to_app/assets/2014/11/09/fname.jpg
        # create folder if not exists
        if not os.path.exists(full_folder_path):
            os.makedirs(full_folder_path)

        img_filename = "%s-%s.png" % (oid, slugify(title))

        # full file path
        full_file_path = os.path.join(full_folder_path, img_filename)

        # download the thumbnail
        thumb_url = "http://docs.google.com/viewer?url=%s&a=bi&pagenumber=1&w=100" % url
        imgstr = urllib2.urlopen(thumb_url).read()

        with open(full_file_path, "w") as f:
            f.write(imgstr)

        # update database => 1. thumb_url: lokasi ke gambar 2. thumb_updated: terakhir update
        # nanti di halaman index, tampilkan data yang ada thumb_updated saja
        fpath = os.path.join(date_folder, img_filename)
        pdfdb.pdf.update({"_id": ObjectId(oid)}, {"$set": {"fpath": fpath, "thumb_updated": datetime.datetime.now()}})

        return "sukses"


@app.route("/admin/inject-single-url", methods=["GET", "POST"])
def admin_single_url_inject():
    """
    input: url path to pdf file
    process: download thumbnail, add title, snippet and url, also keyword (optional)
    post: input into database

    perlukah pdfbox disini????
    """
    if request.method == "POST":
        added = datetime.datetime.now()
        title = request.form["title"]
        snippet = request.form["snippet"]
        url = request.form["url"]
        keyword = title

        # insert database dengan 5 data di atas
        pdfdb = c["pdfs"]
        oid = pdfdb.pdf.insert({
                "added": added,
                "title": title,
                "snippet": snippet,
                "url": url,
                "keyword": keyword,
            })
        # print "sukses"

        # buat folder path dulu
        # simpan di folder dgn format => thn/bln/tanggal
        # app folder
        app_folder = os.getcwd()
        # get year/month/date
        date_folder = datetime.datetime.now().strftime("%Y/%m/%d")
        # joined both
        full_folder_path = os.path.join(app_folder, "assets", date_folder)  # ~/path_to_app/assets/2014/11/09/fname.jpg
        # create folder if not exists
        if not os.path.exists(full_folder_path):
            os.makedirs(full_folder_path)

        img_filename = "%s-%s.png" % (oid, slugify(title))

        # full file path
        full_file_path = os.path.join(full_folder_path, img_filename)

        # download the thumbnail
        thumb_url = "http://docs.google.com/viewer?url=%s&a=bi&pagenumber=1&w=100" % url
        imgstr = urllib2.urlopen(thumb_url).read()

        with open(full_file_path, "w") as f:
            f.write(imgstr)

        # update database => 1. thumb_url: lokasi ke gambar 2. thumb_updated: terakhir update
        # nanti di halaman index, tampilkan data yang ada thumb_updated saja
        fpath = os.path.join(date_folder, img_filename)
        pdfdb.pdf.update({"_id": ObjectId(oid)}, {"$set": {"fpath": fpath, "thumb_updated": datetime.datetime.now()}})

        return "sukses %s %s %s" % (url, title, snippet)
    return render_template("admin/admin_inject_single_url.html")


@app.route("/admin/incoming-search-term")
@admin_login_required
def incoming_search_term():
    """
    list of all new incoming search term
    """
    pass


@app.route("/admin/stats")
@admin_login_required
def stats():
    """
    isinya tentang statistik yang diperlukan
    setiap kali visitor datang ke halaman search
    update db terms: {$inc: {hits: 1}}
    """
    return render_template("admin/admin_stats.html")


@app.route("/admin/update-on-the-fly", methods=["POST"])
@admin_login_required
def update_on_the_fly():
    if request.method == "POST":
        oid = request.form["oid"]
        title = request.form["title"]
        # update database
        pdfdb = c["pdfs"]
        pdfdb.pdf.update({"_id": ObjectId(oid)}, {"$set": {"title": title}})
        return "sukses"


@app.route("/admin/abuse-report")
@admin_login_required
def admin_report_abuse():
    admindb = c["admindb"]
    data = admindb.abuse.find().sort("_id", -1).limit(10)
    return render_template("admin/admin_abuse_report.html", data=data)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    form = AdminLoginForm()

    if "admin" in session:
        return redirect(url_for("admin"))

    if request.method == "POST":
        if form.validate() == False:
            flash("invalid credentials")
            return render_template("admin/login.html", form=form)
        else:
            session["admin"] = form.email.data
            flash("Anda sudah berhasil masuk, selamat!", category="info")
            return redirect(request.args.get("next") or url_for("admin"))
    elif request.method == "GET":
        return render_template("/admin/login.html", form=form)


@app.route("/admin/logout")
def admin_logout():
    if "admin" not in session:
        return redirect(url_for("admin_login"))
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/users/login", methods=["GET", "POST"])
def users_login():
    form = UserLoginForm()
    error = None

    if "username" in session:
        return redirect(url_for("users"))

    if request.method == "POST":
        # if username not exist in dbase, failed
        if not dbentity.users.find_one({"username": form.username.data}):
            error = "Username is not registered."
            return render_template("/users/login.html", form=form, error=error)
        # if password mismatch with dbase, failed
        elif dbentity.users.find_one({"username": form.username.data})["password"] != form.password.data:
            error = "Password mismatch!"
            return render_template("/users/login.html", form=form, error=error)
        # true semua
        else:
            session["username"] = form.username.data
            return redirect(request.args.get("next") or url_for("index"))
    return render_template("/users/login.html", form=form)


@app.route("/users/<username>/profile", methods=["GET", "POST"])
@user_login_required
def users_profile(username):
    # pakenya tetep db.user, biar ngumpul jadi satu
    data = db.user.find_one({"username": session.get("username")})
    return render_template("users/profile.html", data=data)


@app.route("/users/<username>")
def users_public_view(username):
    """ this is for public view
    contains:
    all the picture uploaded.
    """
    dbuser = c["entities"]
    data = dbuser.users.find_one({"username": session.get("username")})
    try:
        favorites = dbuser.users.find_one({"username": username})["favorited"]
        favorites = list(set(favorites))  # unique only
    except:
        favorites = []

    # check if books have thumbnail, resouce? oid
    pdfdb = c["pdfs"]
    thumbs = []
    images = []
    titles = []
    if favorites:
        for i in favorites:
            # get the data
            datafavorites = pdfdb.pdf.find_one({"_id": ObjectId(i)})
            # jika ada fpath (thumbnail tersedia)
            if datafavorites.has_key("fpath"):
                image_path = datafavorites["fpath"]
                title = slugify(datafavorites["title"])

                thumbs.append(True)
                images.append(image_path)
                titles.append(title)
            else:
                title = slugify(datafavorites["title"])

                thumbs.append(False)
                images.append("")
                titles.append(title)

    # zip it
    favorites = zip(favorites, thumbs, images, titles)
    # print favorites

    return render_template("users/users_public_view.html", data=data, favorites=favorites, username=username)


@app.route("/users/logout")
def users_logout():
    if "username" not in session:
        return redirect(url_for("users_login"))
    session.pop("username", None)
    return redirect(url_for("index"))


@app.route("/users")
@user_login_required
def users():
    user = session["username"]
    # if username == admin: redirect to admin page
    # return render_template("/users/index.html", user=user)
    return redirect("/", 301)

@app.route("/users/register", methods=["GET", "POST"])
def users_register():
    form = UserRegisterForm()
    mail = Mail(app)
    error = None

    if request.method == "POST":
        # if username is blank
        if not form.username.data:
            error = "Username can't be empty!"
            return render_template("/users/register.html", form=form, error=error)
        # elif email is blank
        elif not form.email.data:
            error = "Email can't be empty!"
            return render_template("/users/register.html", form=form, error=error)
        # elif no password
        elif not form.password.data:
            error = "Please supply a password!"
            return render_template("/users/register.html", form=form, error=error)
        # is email already exists, failed
        elif form.username.data in ["admin", "banteng"]:
            error = "You can't use this username, try something else."
            return render_template("/users/register.html", form=form, error=error)
        elif dbentity.users.find_one({"email": form.email.data}):
            error = "Email is already taken, please choose another."
            return render_template("/users/register.html", form=form, error=error)
        elif dbentity.users.find_one({"username": form.username.data}):
            error = "Username is already taken, please choose another."
            return render_template("/users/register.html", form=form, error=error)
        elif "@" in form.username.data:
            error = "Don't use email as username. Pick another one!"
            return render_template("/users/register.html", form=form, error=error)
        else:
            # simpan session username
            session["username"] = form.username.data
            # simpan data
            dbentity.users.insert({
                                 "username": form.username.data,
                                 "password": form.password.data,
                                 "email": form.email.data,
                                 "joined_at": datetime.datetime.now(),
                                 })
            # send email
            emailstring = """
            Thank you for registering with example.com.

            Here is your credential info, please keep it secret:

            username: %s
            password: %s

            Regards,

            wallgigs.com
            """ % (form.username.data, form.password.data)
            msg = Message("Welcome to example.com", sender="info@example.com", recipients=[form.email.data])
            msg.body = emailstring
            # mail.send(msg)
            # return redirect(request.args.get("next") or url_for("users"))
            return redirect(request.args.get("next") or url_for("index"))
    return render_template("/users/register.html", form=form)


@app.route("/sitemap")
def sitemap():
    pdftermsdb = c["pdfterms"]
    # skip_number = random.randint(0, pdftermsdb.term.find().count()-50)
    # data = pdftermsdb.term.find().skip(skip_number).limit(50)
    data =pdftermsdb.term.find().sort("_id", -1)
    sitemap_xml = render_template("sitemap.xml", data=data)
    response = make_response(sitemap_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


@app.route('/recent.atom')
def recent_feed():
    # http://werkzeug.pocoo.org/docs/contrib/atom/ 
    # wajibun: id(link) dan updated
    # feed = AtomFeed('Recent Articles',
    #                feed_url = request.url, url=request.url_root)
    # data = datas
    # for d in data:
    #    feed.add(d['nama'], content_type='html', id=d['id'], updated=datetime.datetime.now())
    # return feed.get_response()
    pass


def grab(url):
    # print 'Starting %s' % url
    # http request
    opener = urllib2.build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    html = opener.open(url).read()
    # soup coming in
    soup = BeautifulSoup(html)
    # parsing
    ## get title
    titles = [i.get_text() for i in soup.findAll('h3', attrs={'class': 'r'})]
    ## get url
    ahrefs = [i.find('a')['href'] for i in soup.findAll('h3',
                                                        attrs={'class': 'r'})]
    pattern = re.compile(r"=(.*?)&")
    urls = [re.search(pattern, i).group(1) for i in ahrefs]
    ## prevent from string quoting on url
    urls = [unquote(url) for url in urls]
    ## get snippet
    snippets = [i.get_text() for i in soup.findAll('span',
                                                   attrs={'class': 'st'})]
    ## gathering data
    container = []
    ## format data
    if len(titles) == len(urls) == len(snippets):
        for i in range(len(titles)):
            container.append({'title': titles[i], 'url': urls[i],
                              'snippet': snippets[i]})
    return container
