import { prisma } from '@/lib/prisma'
import { notFound } from 'next/navigation'
import { AddToCartButton } from '@/components/AddToCartButton'
import { formatPrice } from '@/lib/utils'
import Image from 'next/image'

export const revalidate = 60

async function getProduct(id: string) {
  return await prisma.product.findUnique({
    where: { id },
  })
}

export default async function ProductPage({
  params,
}: {
  params: { id: string }
}) {
  const product = await getProduct(params.id)

  if (!product) {
    notFound()
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="grid gap-8 md:grid-cols-2">
        <div className="relative aspect-square overflow-hidden rounded-lg">
          <Image
            src={product.image}
            alt={product.name}
            fill
            className="object-cover"
          />
        </div>
        
        <div>
          <h1 className="mb-4 text-4xl font-bold">{product.name}</h1>
          <p className="mb-4 text-3xl font-semibold text-primary-600">
            {formatPrice(product.price)}
          </p>
          <p className="mb-6 text-gray-600">{product.description}</p>
          
          <div className="mb-6">
            <span className="text-sm text-gray-500">Category: </span>
            <span className="font-medium">{product.category}</span>
          </div>
          
          <div className="mb-6">
            <span className="text-sm text-gray-500">Stock: </span>
            <span className="font-medium">
              {product.stock > 0 ? `${product.stock} available` : 'Out of stock'}
            </span>
          </div>
          
          <AddToCartButton product={product} />
        </div>
      </div>
    </div>
  )
}