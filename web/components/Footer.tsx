import Link from 'next/link'

export function Footer() {
  return (
    <footer className="border-t bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <div className="grid gap-8 md:grid-cols-4">
          <div>
            <h3 className="mb-4 font-bold">Sharrowkin Market</h3>
            <p className="text-sm text-gray-600">
              Your trusted marketplace for quality products
            </p>
          </div>
          
          <div>
            <h4 className="mb-4 font-semibold">Shop</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/products">All Products</Link></li>
              <li><Link href="/products?category=electronics">Electronics</Link></li>
              <li><Link href="/products?category=clothing">Clothing</Link></li>
            </ul>
          </div>
          
          <div>
            <h4 className="mb-4 font-semibold">Support</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/help">Help Center</Link></li>
              <li><Link href="/contact">Contact Us</Link></li>
              <li><Link href="/returns">Returns</Link></li>
            </ul>
          </div>
          
          <div>
            <h4 className="mb-4 font-semibold">Legal</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/privacy">Privacy Policy</Link></li>
              <li><Link href="/terms">Terms of Service</Link></li>
            </ul>
          </div>
        </div>
        
        <div className="mt-8 border-t pt-8 text-center text-sm text-gray-600">
          © 2026 Sharrowkin Marketplace. All rights reserved.
        </div>
      </div>
    </footer>
  )
}