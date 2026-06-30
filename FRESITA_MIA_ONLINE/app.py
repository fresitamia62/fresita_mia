from flask import Flask, render_template, redirect, url_for, session, request, send_file
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
import pandas as pd
from io import BytesIO
from datetime import date

app = Flask(__name__, static_folder="static")
app.secret_key = "fresita_mia_secreta"

app.config["MYSQL_HOST"] = os.environ.get("MYSQLHOST")
app.config["MYSQL_USER"] = os.environ.get("MYSQLUSER")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQLPASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQLDATABASE")
app.config["MYSQL_PORT"] = int(os.environ.get("MYSQLPORT"))

mysql = MySQL(app)


def obtener_cliente():
    if "id_usuario" in session:
        return session["id_usuario"], None

    if "invitado_id" not in session:
        session["invitado_id"] = str(uuid.uuid4())

    return None, session["invitado_id"]


def obtener_carrito(cursor):
    id_usuario, invitado_id = obtener_cliente()

    if id_usuario:
        cursor.execute("SELECT id_carrito FROM carrito WHERE id_usuario = %s", (id_usuario,))
    else:
        cursor.execute("SELECT id_carrito FROM carrito WHERE invitado_id = %s", (invitado_id,))

    carrito = cursor.fetchone()

    if carrito:
        return carrito[0], id_usuario, invitado_id

    if id_usuario:
        cursor.execute("INSERT INTO carrito (id_usuario) VALUES (%s)", (id_usuario,))
    else:
        cursor.execute("INSERT INTO carrito (invitado_id) VALUES (%s)", (invitado_id,))

    mysql.connection.commit()

    return cursor.lastrowid, id_usuario, invitado_id


@app.route("/")
def inicio():
    return render_template("index.html")

@app.route("/menu")
def menu():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT * FROM productos
        ORDER BY nombre
    """)
    productos = cursor.fetchall()
    cursor.close()

    orden_categorias = [
    "Fresas con crema",
    "Rebanafresa",
    "Mini Hotcakes",
    "Fresas Combinadas",
    "Mega Antojo",
    "Antojos",
    "Pasteles"
]

    productos_por_categoria = {}

    # Primero agrega las categorías principales
    for categoria in orden_categorias:
        productos_por_categoria[categoria] = []

    # Después acomoda cada producto en su categoría
    for producto in productos:
        categoria = producto[6]

        if categoria not in productos_por_categoria:
            productos_por_categoria[categoria] = []

        productos_por_categoria[categoria].append(producto)

    # Elimina categorías vacías
    productos_por_categoria = {
        categoria: lista
        for categoria, lista in productos_por_categoria.items()
        if lista
    }

    return render_template("menu.html", productos_por_categoria=productos_por_categoria)

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contraseña = request.form["contraseña"]
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]

        contraseña_segura = generate_password_hash(contraseña)

        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO usuarios (usuario, contraseña, nombre_completo, telefono, rol)
            VALUES (%s, %s, %s, %s, 'cliente')
        """, (usuario, contraseña_segura, nombre, telefono))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for("login"))

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contraseña = request.form["contraseña"]

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user[2], contraseña):
            session.pop("invitado_id", None)

            session["id_usuario"] = user[0]
            session["usuario"] = user[1]
            session["rol"] = user[5]

            if user[5] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("perfil"))

        return "Usuario o contraseña incorrectos"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("inicio"))


@app.route("/perfil")
def perfil():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_usuario = session["id_usuario"]

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id_pedido, total, estado, fecha_pedido
        FROM pedidos
        WHERE id_usuario = %s
        ORDER BY id_pedido DESC
    """, (id_usuario,))

    pedidos = cursor.fetchall()
    cursor.close()

    return render_template("perfil.html", pedidos=pedidos)


@app.route("/agregar_carrito/<int:id_producto>")
def agregar_carrito(id_producto):
    cursor = mysql.connection.cursor()

    id_carrito, id_usuario, invitado_id = obtener_carrito(cursor)

    cursor.execute("""
        SELECT id_detalle, cantidad
        FROM detalle_carrito
        WHERE id_carrito = %s AND id_producto = %s
    """, (id_carrito, id_producto))

    producto_existente = cursor.fetchone()

    if producto_existente:
        nueva_cantidad = producto_existente[1] + 1
        cursor.execute("""
            UPDATE detalle_carrito
            SET cantidad = %s
            WHERE id_detalle = %s
        """, (nueva_cantidad, producto_existente[0]))
    else:
        cursor.execute("""
            INSERT INTO detalle_carrito (id_carrito, id_producto, cantidad)
            VALUES (%s, %s, 1)
        """, (id_carrito, id_producto))

    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("menu"))


@app.route("/carrito")
def ver_carrito():
    cursor = mysql.connection.cursor()

    id_carrito, id_usuario, invitado_id = obtener_carrito(cursor)

    cursor.execute("""
        SELECT
            dc.id_detalle,
            p.nombre,
            p.precio,
            dc.cantidad,
            ((p.precio + IFNULL(dc.precio_extras,0)) * dc.cantidad) AS total_producto,
            dc.tamano,
            dc.toppings,
            dc.jarabes,
            dc.extras,
            dc.precio_extras,
            dc.pastel,
            dc.frutas,
            dc.base_preparado,
            dc.comentarios
        FROM detalle_carrito dc
        INNER JOIN productos p
            ON dc.id_producto = p.id_producto
        WHERE dc.id_carrito = %s
    """, (id_carrito,))

    productos_carrito = cursor.fetchall()
    cursor.close()

    total = sum(float(producto[4]) for producto in productos_carrito)

    return render_template(
        "carrito.html",
        productos_carrito=productos_carrito,
        total=total
    )


@app.route("/aumentar/<int:id_detalle>")
def aumentar_cantidad(id_detalle):
    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE detalle_carrito
        SET cantidad = cantidad + 1
        WHERE id_detalle = %s
    """, (id_detalle,))
    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("ver_carrito"))


@app.route("/disminuir/<int:id_detalle>")
def disminuir_cantidad(id_detalle):
    cursor = mysql.connection.cursor()

    cursor.execute("SELECT cantidad FROM detalle_carrito WHERE id_detalle = %s", (id_detalle,))
    producto = cursor.fetchone()

    if producto and producto[0] > 1:
        cursor.execute("""
            UPDATE detalle_carrito
            SET cantidad = cantidad - 1
            WHERE id_detalle = %s
        """, (id_detalle,))
    else:
        cursor.execute("DELETE FROM detalle_carrito WHERE id_detalle = %s", (id_detalle,))

    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("ver_carrito"))


@app.route("/eliminar/<int:id_detalle>")
def eliminar_producto(id_detalle):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM detalle_carrito WHERE id_detalle = %s", (id_detalle,))
    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("ver_carrito"))


@app.route("/vaciar_carrito")
def vaciar_carrito():
    cursor = mysql.connection.cursor()

    id_carrito, id_usuario, invitado_id = obtener_carrito(cursor)

    cursor.execute("DELETE FROM detalle_carrito WHERE id_carrito = %s", (id_carrito,))
    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("ver_carrito"))


@app.route("/finalizar_compra", methods=["GET", "POST"])
def finalizar_compra():
    cursor = mysql.connection.cursor()

    id_carrito, id_usuario, invitado_id = obtener_carrito(cursor)

    cursor.execute("""
        SELECT
            dc.id_detalle,
            p.id_producto,
            p.nombre,
            p.precio,
            dc.cantidad,
            ((p.precio + IFNULL(dc.precio_extras, 0)) * dc.cantidad) AS total_producto,
            dc.tamano,
            dc.toppings,
            dc.jarabes,
            dc.extras,
            dc.precio_extras,
            dc.comentarios,
            dc.pastel,
            dc.frutas,
            dc.base_preparado
        FROM detalle_carrito dc
        INNER JOIN productos p ON dc.id_producto = p.id_producto
        WHERE dc.id_carrito = %s
    """, (id_carrito,))

    productos_carrito = cursor.fetchall()
    total = sum(float(producto[5]) for producto in productos_carrito)

    if not productos_carrito:
        cursor.close()
        return redirect(url_for("ver_carrito"))

    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        tipo_entrega = request.form["tipo_entrega"]
        direccion = request.form["direccion"]
        metodo_pago = request.form["metodo_pago"]
        comentarios = request.form.get("comentarios", "")

        if tipo_entrega == "Recoger en local":
            costo_envio = 0
        elif tipo_entrega == "Zona Centro":
            costo_envio = 15
        elif tipo_entrega == "Fraccionamientos":
            costo_envio = 15
        elif tipo_entrega == "Deportiva, Independencia, Planetaria":
            costo_envio = 15
        elif tipo_entrega == "Revolución, San Juanita, San José":
            costo_envio = 20
        elif tipo_entrega == "Praderas":
            costo_envio = 30
        else:
            costo_envio = 0

        total_final = total + costo_envio

        cursor.execute("""
            INSERT INTO pedidos
            (id_usuario, invitado_id, nombre_cliente, telefono, tipo_entrega, direccion, metodo_pago, comentarios, costo_envio, total, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente')
        """, (
            id_usuario,
            invitado_id,
            nombre,
            telefono,
            tipo_entrega,
            direccion,
            metodo_pago,
            comentarios,
            costo_envio,
            total_final
        ))

        id_pedido = cursor.lastrowid

        for producto in productos_carrito:
            cursor.execute("""
                INSERT INTO detalle_pedido
                (id_pedido, id_producto, cantidad, precio_unitario, tamano, toppings, jarabes, extras, precio_extras, comentarios, pastel, frutas, base_preparado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                id_pedido,
                producto[1],
                producto[4],
                producto[3],
                producto[6],
                producto[7],
                producto[8],
                producto[9],
                producto[10],
                producto[11],
                producto[12],
                producto[13],
                producto[14]
            ))

        cursor.execute("DELETE FROM detalle_carrito WHERE id_carrito = %s", (id_carrito,))

        mysql.connection.commit()
        cursor.close()

        return render_template("gracias.html", id_pedido=id_pedido)

    cursor.close()

    return render_template("finalizar_compra.html", total=total)


@app.route("/eventos")
def eventos():
    return render_template("eventos.html")


@app.route("/admin")
def admin():
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM pedidos
        WHERE DATE(fecha_pedido) = CURDATE()
    """)
    ventas_hoy = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM pedidos
        WHERE DATE(fecha_pedido) = CURDATE()
    """)
    pedidos_hoy = cursor.fetchone()[0]

    cursor.execute("""
        SELECT p.nombre, SUM(dp.cantidad) AS total_vendido
        FROM detalle_pedido dp
        INNER JOIN productos p ON dp.id_producto = p.id_producto
        INNER JOIN pedidos pe ON dp.id_pedido = pe.id_pedido
        WHERE DATE(pe.fecha_pedido) = CURDATE()
        GROUP BY p.nombre
        ORDER BY total_vendido DESC
        LIMIT 1
    """)
    producto_mas_vendido = cursor.fetchone()

    cursor.execute("""
        SELECT p.nombre, SUM(dp.cantidad) AS total_vendido
        FROM detalle_pedido dp
        INNER JOIN productos p ON dp.id_producto = p.id_producto
        INNER JOIN pedidos pe ON dp.id_pedido = pe.id_pedido
        GROUP BY p.nombre
        ORDER BY total_vendido DESC
        LIMIT 5
    """)
    top_productos = cursor.fetchall()

    cursor.execute("""
        SELECT id_pedido,
               nombre_cliente,
               telefono,
               tipo_entrega,
               direccion,
               metodo_pago,
               comentarios,
               total,
               estado,
               fecha_pedido
        FROM pedidos
        WHERE cerrado = 0
        ORDER BY id_pedido DESC
    """)

    pedidos = cursor.fetchall()
    cursor.close()

    return render_template(
        "admin.html",
        pedidos=pedidos,
        ventas_hoy=ventas_hoy,
        pedidos_hoy=pedidos_hoy,
        producto_mas_vendido=producto_mas_vendido,
        top_productos=top_productos
    )


@app.route("/admin/productos")
def admin_productos():
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id_producto, nombre, descripcion, precio, imagen, estado, categoria
        FROM productos
        ORDER BY categoria, nombre
    """)
    productos = cursor.fetchall()
    cursor.close()

    return render_template("admin_productos.html", productos=productos)


@app.route("/admin/cambiar_estado_producto/<int:id_producto>")
def cambiar_estado_producto(id_producto):
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT estado FROM productos WHERE id_producto = %s", (id_producto,))
    producto = cursor.fetchone()

    if producto:
        estado_actual = producto[0]
        nuevo_estado = "agotado" if estado_actual == "disponible" else "disponible"

        cursor.execute("""
            UPDATE productos
            SET estado = %s
            WHERE id_producto = %s
        """, (nuevo_estado, id_producto))

        mysql.connection.commit()

    cursor.close()
    return redirect(url_for("admin_productos"))


@app.route("/admin/cerrar_dia")
def cerrar_dia():
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE pedidos
        SET cerrado = 1
        WHERE DATE(fecha_pedido) = CURDATE()
    """)
    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("admin"))


@app.route("/admin/exportar_pedidos_hoy")
def exportar_pedidos_hoy():
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id_pedido, nombre_cliente, telefono, tipo_entrega, direccion,
               metodo_pago, comentarios, costo_envio, total, estado, fecha_pedido
        FROM pedidos
        WHERE DATE(fecha_pedido) = CURDATE()
        ORDER BY id_pedido ASC
    """)
    pedidos = cursor.fetchall()
    cursor.close()

    columnas = [
        "ID Pedido", "Cliente", "Teléfono", "Entrega", "Dirección",
        "Método de pago", "Comentarios", "Costo envío", "Total",
        "Estado", "Fecha"
    ]

    df = pd.DataFrame(pedidos, columns=columnas)

    archivo = BytesIO()
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Pedidos de hoy")

    archivo.seek(0)

    return send_file(
        archivo,
        as_attachment=True,
        download_name=f"pedidos_hoy_{date.today()}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/actualizar_estado/<int:id_pedido>", methods=["POST"])
def actualizar_estado(id_pedido):
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    nuevo_estado = request.form["estado"]

    cursor = mysql.connection.cursor()
    cursor.execute("""
        UPDATE pedidos
        SET estado = %s
        WHERE id_pedido = %s
    """, (nuevo_estado, id_pedido))

    mysql.connection.commit()
    cursor.close()

    return redirect(url_for("admin"))


@app.route("/detalle_pedido/<int:id_pedido>")
def detalle_pedido(id_pedido):
    if "rol" not in session or session["rol"] != "admin":
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT nombre_cliente, telefono, direccion, metodo_pago, total, estado
        FROM pedidos
        WHERE id_pedido = %s
    """, (id_pedido,))
    pedido = cursor.fetchone()

    cursor.execute("""
        SELECT
            p.nombre,
            dp.cantidad,
            dp.precio_unitario,
            ((dp.precio_unitario + IFNULL(dp.precio_extras,0)) * dp.cantidad) AS subtotal,
            dp.tamano,
            dp.toppings,
            dp.jarabes,
            dp.extras,
            dp.precio_extras,
            dp.comentarios,
            dp.pastel,
            dp.frutas,
            dp.base_preparado
        FROM detalle_pedido dp
        INNER JOIN productos p
            ON dp.id_producto = p.id_producto
        WHERE dp.id_pedido = %s
    """, (id_pedido,))

    productos = cursor.fetchall()
    cursor.close()

    return render_template(
        "detalle_pedido.html",
        pedido=pedido,
        productos=productos,
        id_pedido=id_pedido
    )


@app.route("/personalizar_producto/<int:id_producto>", methods=["GET", "POST"])
def personalizar_producto(id_producto):
    cursor = mysql.connection.cursor()

    cursor.execute("SELECT * FROM productos WHERE id_producto = %s", (id_producto,))
    producto = cursor.fetchone()

    if request.method == "POST":
        nombre_producto = producto[1]

        tamano = request.form.get("tamano", "No aplica")
        toppings = ", ".join(request.form.getlist("toppings"))
        jarabes = ", ".join(request.form.getlist("jarabes"))
        extras = ", ".join(request.form.getlist("extras"))
        pastel = request.form.get("pastel", "No aplica")
        frutas = ", ".join(request.form.getlist("frutas"))
        base_preparado = request.form.get("base_preparado", "No aplica")
        precio_extras = request.form.get("precio_extras", 0)
        comentarios = request.form.get("comentarios", "")

        # Caso especial: Rebana Fresa
        if nombre_producto == "Rebana Fresa":
            tamano = "No aplica"
            toppings = "No aplica"
            jarabes = "No aplica"
            extras = "No aplica"
            frutas = "No aplica"
            base_preparado = "No aplica"
            comentarios = "Pastel elegido: " + pastel

        # Caso especial: Rebana Fresa Especial
        elif nombre_producto == "Rebana Fresa Especial":
            tamano = "No aplica"
            toppings = "No aplica"
            jarabes = "No aplica"
            extras = "No aplica"
            frutas = "No aplica"
            base_preparado = "No aplica"
            comentarios = "Pastel elegido: " + pastel

        id_carrito, id_usuario, invitado_id = obtener_carrito(cursor)

        cursor.execute("""
            INSERT INTO detalle_carrito 
            (id_carrito, id_producto, cantidad, tamano, toppings, jarabes, extras, precio_extras, comentarios, pastel, frutas, base_preparado)
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            id_carrito,
            id_producto,
            tamano,
            toppings,
            jarabes,
            extras,
            precio_extras,
            comentarios,
            pastel,
            frutas,
            base_preparado
        ))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for("ver_carrito"))

    cursor.close()
    return render_template("personalizar_producto.html", producto=producto)

@app.route("/consultar_pedido", methods=["GET", "POST"])
def consultar_pedido():
    pedido = None

    if request.method == "POST":
        id_pedido = request.form["id_pedido"]
        telefono = request.form["telefono"]

        cursor = mysql.connection.cursor()
        cursor.execute("""
            SELECT id_pedido, nombre_cliente, total, estado, fecha_pedido
            FROM pedidos
            WHERE id_pedido = %s AND telefono = %s
        """, (id_pedido, telefono))

        pedido = cursor.fetchone()
        cursor.close()

    return render_template("consultar_pedido.html", pedido=pedido)

if __name__ == "__main__":
    app.run(debug=True)
