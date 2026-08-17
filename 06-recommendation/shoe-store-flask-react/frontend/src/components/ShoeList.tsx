import React, { useEffect, useState } from "react";
import { Box, Skeleton } from "@mui/material";
import ShoeCard from "./ShoeCard";
import Shoe1 from "../assets/shoe1Red.avif";
import Shoe2 from "../assets/shoe2Yellow.avif";
import Shoe3 from "../assets/shoe3Black.avif";
import Shoe4 from "../assets/shoe4Brown.avif";
import Shoe5 from "../assets/greySimilarShoe1.png";
import Shoe6 from "../assets/greenSimilarShoe1.png";
import "./ShoeList.css";
import axios from "axios";

interface Shoe {
  id: number;
  PRODUCT_NAME: string;
  BRAND: string;
  CLASS: string;
  TYPE: string;
  MATERIAL: string;
  COLOR: string;
  SIZE: number;
  SKU: string;
  description: string;
  PRICE: number;
  RATING: number;
  CITY: string;
  STORE_ID: number;
  COLORS: string[];
  DESCRIPTION: string;
}

const imageMap: Record<string, string> = {
  "ZEN-5999": Shoe1,
  "RUN-4723": Shoe2,
  "ZEN-8968": Shoe3,
  "RUN-7569": Shoe4,
  "RUN-1083": Shoe5,
  "LOO-1505": Shoe6,
};

const ShoeList: React.FC = () => {
  const [shoes, setShoes] = useState<Shoe[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    axios.get("/api/products")
      .then((res) => {
        setShoes(res.data.products);
      })
      .catch((err) => {
        console.error("Error fetching shoes:", err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return (
    <Box className="shoe-list">
      {loading
        ? Array.from(new Array(6)).map((_, index) => (
            <Box className="shoe-card-container" key={index}>
              <Skeleton variant="rectangular" width={300} height={200} />
              <Skeleton width="60%" />
              <Skeleton width="40%" />
            </Box>
          ))
        : shoes.map((shoe) => (
            <Box className="shoe-card-container" key={shoe.id}>
              <ShoeCard
                id={shoe.SKU}
                image={imageMap[shoe.SKU]}
                PRODUCT_NAME={shoe.PRODUCT_NAME}
                PRICE={shoe.PRICE}
                RATING={shoe.RATING}
                COLOR={shoe.COLOR}
                BRAND={shoe.BRAND}
                CLASS={shoe.CLASS}
                TYPE={shoe.TYPE}
                MATERIAL={shoe.MATERIAL}
                SIZE={shoe.SIZE}
                SKU={shoe.SKU}
                CITY={shoe.CITY}
                STORE_ID={shoe.STORE_ID}
                COLORS={shoe.COLORS}
                DESCRIPTION={shoe.DESCRIPTION}
              />
            </Box>
          ))}
    </Box>
  );
};

export default ShoeList;
