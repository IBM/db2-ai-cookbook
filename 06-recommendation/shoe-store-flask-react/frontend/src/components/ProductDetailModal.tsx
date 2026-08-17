import React from "react";
import {
    Dialog,
    DialogTitle,
    DialogContent,
    Typography,
    Rating,
    Box,
    IconButton,
    Button,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

interface Product {
    SKU: string;
    PRODUCT_NAME: string;
    PRICE: number;
    BRAND: string;
    COLOR: string;
    RATING: number;
}

interface ProductDetailModalProps {
    open: boolean;
    onClose: () => void;
    product: Product | null;
    imageUrl: string;
}

const ProductDetailModal: React.FC<ProductDetailModalProps> = ({
    open,
    onClose,
    product,
    imageUrl,
}) => {
    if (!product) {
        return null;
    }

    const handleAddToCart = () => {
        console.log(`Added ${product.PRODUCT_NAME} (SKU: ${product.SKU}) to cart.`);
        onClose();
    };

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="h6" fontWeight="bold">
                        Product Details
                    </Typography>
                    <IconButton onClick={onClose}>
                        <CloseIcon />
                    </IconButton>
                </Box>
            </DialogTitle>
            <DialogContent dividers>
                <Box
                    display="flex"
                    flexDirection={{ xs: "column", sm: "row" }}
                    gap={3}
                    alignItems="center"
                >
                    <Box flexShrink={0}>
                        <img
                            src={imageUrl}
                            alt={product.PRODUCT_NAME}
                            style={{
                                maxWidth: "200px",
                                maxHeight: "200px",
                                objectFit: "contain",
                            }}
                        />
                    </Box>
                    <Box>
                        <Typography variant="h5" fontWeight="bold" gutterBottom>
                            {product.PRODUCT_NAME}
                        </Typography>
                        <Typography variant="subtitle1" color="text.secondary">
                            Brand: {product.BRAND}
                        </Typography>
                        <Typography variant="h6" mt={1}>
                            ${product.PRICE.toFixed(2)}
                        </Typography>
                        <Rating value={product.RATING} precision={0.5} readOnly sx={{ mt: 1 }} />
                        <Typography variant="body1" mt={1}>
                            Color: {product.COLOR}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                            SKU: {product.SKU}
                        </Typography>
                        {/* Add to Cart Button */}
                        <Button
                            variant="contained"
                            color="primary"
                            fullWidth
                            sx={{ mt: 3 }}
                            onClick={handleAddToCart}
                        >
                            Add to Cart
                        </Button>
                    </Box>
                </Box>
            </DialogContent>
        </Dialog>
    );
};

export default ProductDetailModal;