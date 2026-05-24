import Link from 'next/link'
import Image from 'next/image'
import { formatPrice } from '@/lib/utils'

interface Product {
  id: string
  name: string
  price: number
  image: string
  category: string
}

export function ProductCard({ product }: { product: Product }) {
  return (
    <Link
      href={`/products/${product.id}`}
      className="group overflow-hidden rounded-lg border bg-white transition hover:shadow-lg"
    >
      <div className="relative aspect-square overflow-hidden">
        <Image
          src={product.image}
          alt={product.name}
          fill
          className="object-cover transition group-hover:scale-105"
        />
      </div>
      <div className="p-4">
        <p className="mb-1 text-sm text-gray-500">{product.category}</p>
        <h3 className="mb-2 font-semibold">{product.name}</h3>
        <p className="text-lg font-bold text-primary-600">
          {formatPrice(product.price)}
        </p>
      </div>
    </Link>
  )
}