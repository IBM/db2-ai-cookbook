from flask import Blueprint, jsonify
from app.db import db2_connect
import ibm_db
from flask import request

products_bp = Blueprint('products', __name__)

@products_bp.route('/api/products', methods=['GET'])
def get_products():
    conn = db2_connect()
    if conn is None:
        return jsonify({"error": "DB connection failed"}), 500

    try:
        # Fetch 6 products
        sql = "SELECT * FROM s1.sq_shoes FETCH FIRST 3 ROWS ONLY"
        stmt = ibm_db.exec_immediate(conn, sql)

        products = []
        row = ibm_db.fetch_assoc(stmt)
        while row:
            sku = row.get("SKU")

            # Fetch color-size mappings for this product
            color_size_sql = "SELECT COLOR, SIZE FROM s1.shoe_color_sizes WHERE SKU = ?"
            color_stmt = ibm_db.prepare(conn, color_size_sql)
            ibm_db.bind_param(color_stmt, 1, sku)
            ibm_db.execute(color_stmt)

            color_size_map = {}
            available_sizes = set()
            colors = set()

            while True:
                c_row = ibm_db.fetch_assoc(color_stmt)
                if not c_row:
                    break
                color = c_row["COLOR"]
                size = float(c_row["SIZE"])
                color_size_map.setdefault(color, []).append(size)
                available_sizes.add(size)
                colors.add(color)

            color_sizes_list = [{"color": color, "sizes": sorted(sizes)} for color, sizes in color_size_map.items()]

            product = {
                "id": row.get("SKU"),
                "SKU": sku,
                "PRODUCT_NAME": row.get("PRODUCT_NAME"),
                "BRAND": row.get("BRAND"),
                "CLASS": row.get("CLASS"),
                "TYPE": row.get("TYPE"),
                "MATERIAL": row.get("MATERIAL"),
                "COLOR": row.get("COLOR"),
                "WEATHER_RESISTANCE": row.get("WEATHER_RESISTANCE"),
                "ARCH_SUPPORT": row.get("ARCH_SUPPORT"),
                "SIZE": row.get("SIZE"),
                "PRICE": row.get("PRICE"),
                "RATING": row.get("RATING"),
                "STORE_ID": row.get("STORE_ID"),
                "CITY": row.get("CITY"),
                "DESCRIPTION": row.get("DESCRIPTION") or "Perfect for running and outdoor adventures.",
                "AVAILABLE_SIZES": sorted(available_sizes),
                "COLORS": sorted(colors),
                "COLOR_SIZES": color_sizes_list
            }

            products.append(product)
            row = ibm_db.fetch_assoc(stmt)

        return jsonify({"products": products})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        ibm_db.close(conn)


@products_bp.route('/api/products/<string:sku>', methods=['GET'])
def get_product_by_sku(sku):
    conn = db2_connect()
    if conn is None:
        return jsonify({"error": "DB connection failed"}), 500

    try:
        # Fetch main product info
        sql = "SELECT * FROM s1.sq_shoes WHERE SKU = ? FETCH FIRST 1 ROW ONLY"
        stmt = ibm_db.prepare(conn, sql)
        ibm_db.bind_param(stmt, 1, sku)
        ibm_db.execute(stmt)
        row = ibm_db.fetch_assoc(stmt)

        if not row:
            return jsonify({"error": "Product not found"}), 404

        available_sizes, color_sizes_list, colors = fetch_color_size_mapping(conn, sku)

        # Final product response
        product = {
            "id": row.get("SKU"),
            "SKU": row.get("SKU"),
            "PRODUCT_NAME": row.get("PRODUCT_NAME"),
            "BRAND": row.get("BRAND"),
            "CLASS": row.get("CLASS"),
            "TYPE": row.get("TYPE"),
            "MATERIAL": row.get("MATERIAL"),
            "COLOR": row.get("COLOR"),
            "WEATHER_RESISTANCE": row.get("WEATHER_RESISTANCE"),
            "ARCH_SUPPORT": row.get("ARCH_SUPPORT"),
            "SIZE": row.get("SIZE"),
            "PRICE": row.get("PRICE"),
            "RATING": row.get("RATING"),
            "STORE_ID": row.get("STORE_ID"),
            "CITY": row.get("CITY"),
            "DESCRIPTION": row.get("DESCRIPTION") or "Perfect for running and outdoor adventures.",
            "AVAILABLE_SIZES": sorted(available_sizes),
            "COLORS": sorted(colors),
            "COLOR_SIZES": color_sizes_list
        }

        return jsonify(product)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        ibm_db.close(conn)


def fetch_color_size_mapping(conn, sku):
    # Fetch color-size mappings
    color_size_sql = "SELECT COLOR, SIZE FROM s1.shoe_color_sizes WHERE SKU = ?"
    color_stmt = ibm_db.prepare(conn, color_size_sql)
    ibm_db.bind_param(color_stmt, 1, sku)
    ibm_db.execute(color_stmt)
    color_size_map = {}
    available_sizes = set()
    colors = set()
    while True:
        c_row = ibm_db.fetch_assoc(color_stmt)
        if not c_row:
            break
        color = c_row["COLOR"]
        size = float(c_row["SIZE"])
        color_size_map.setdefault(color, []).append(size)
        available_sizes.add(size)
        colors.add(color)
    color_sizes_list = [{"color": color, "sizes": sorted(sizes)} for color, sizes in color_size_map.items()]
    return available_sizes, color_sizes_list, colors


@products_bp.route('/api/products/<string:sku>/recommendations', methods=['GET'])
def get_recommended_products(sku):
    conn = db2_connect()
    if conn is None:
        return jsonify({"error": "DB connection failed"}), 500

    try:
        # Get top 8 closest products based on vector similarity
        sql = """
            SELECT SKU, PRODUCT_NAME, BRAND, PRICE, RATING, COLOR
            FROM (
                SELECT sku,
                       PRODUCT_NAME,
                       BRAND,
                       PRICE,
                       RATING,
                       COLOR,
                       vector_distance(
                           (SELECT embedding FROM s1.sq_shoes WHERE sku = ?),
                           embedding,
                           euclidean) AS distance
                FROM s1.sq_shoes
                WHERE sku <> ?
                ORDER BY distance ASC
                FETCH FIRST 8 ROWS ONLY
            )
        """
        stmt = ibm_db.prepare(conn, sql)
        ibm_db.bind_param(stmt, 1, sku)
        ibm_db.bind_param(stmt, 2, sku)
        ibm_db.execute(stmt)

        recommendations = []
        row = ibm_db.fetch_assoc(stmt)
        while row:
            recommendations.append({
                "SKU": row.get("SKU"),
                "PRODUCT_NAME": row.get("PRODUCT_NAME"),
                "BRAND": row.get("BRAND"),
                "PRICE": row.get("PRICE"),
                "RATING": row.get("RATING"),
                "COLOR": row.get("COLOR")
            })
            row = ibm_db.fetch_assoc(stmt)

        return jsonify({"recommended_products": recommendations})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        ibm_db.close(conn)

@products_bp.route('/api/query/vector-search', methods=['GET'])
def get_vector_search_query():
    query = """
    SELECT SKU, PRODUCT_NAME, BRAND, PRICE, RATING, COLOR
    FROM (
        SELECT sku,
               PRODUCT_NAME,
               BRAND,
               PRICE,
               RATING,
               COLOR,
               vector_distance(
                   (SELECT embedding FROM s1.sq_shoes WHERE sku = ?),
                   embedding,
                   euclidean) AS distance
        FROM s1.sq_shoes
        WHERE sku <> ?
        ORDER BY distance ASC
        FETCH FIRST 8 ROWS ONLY
    )
    """
    return jsonify({"query": query.strip()}), 200
